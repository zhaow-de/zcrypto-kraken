# Order-semantics verification runbook

<a name="order-semantics-verification"></a>

Attended operator procedure for `infra/scripts/kraken-order-semantics-probe.py`, the six-probe protocol re-run demanded by the
memo's **Version re-check rule** ("a fresh ~€0.20 zero-fill + round-trip pass must re-run the
order-semantics probes before the engine trades on the new version" —
`docs/reference/adapter-verification/1.230.0.md`). Nothing trades until the engine is armed by
hand, so it gates **arming**, not merging: the repo may sit on a bumped version indefinitely while
disarmed. It is owed at **every** nautilus-trader bump, before the engine may be armed on that version.

**A pass binds to one exact version string and nothing else** — §1.6 says what that demands of the
pin, and it may need deciding days before anything else here.

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
| Left-resting risk | the harness cancels by client order id on every exit path — the sequence's own teardown, then again while the node stops — and then reads every submitted id back out of the cache once the node has stopped; exit code 3 means something survived that read, and the terminal prints the ids to cancel by hand |
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

Do not instead run the harness on `zcrypto`: it has no interpreter at the version under test, and
putting a probe process beside the live engine on the same host is not worth the convenience.

### 1.4 The account is funded

The probes need enough EUR to (a) let probe 5 buy ~EUR 10 and (b) let the venue accept the resting
margin orders. Check at Kraken → Balances, or let **probe 1** tell you — but read it knowing that
what the account object reports under `spot_account_type=MARGIN` is the adapter's choice and is not
readable from the wheel. It was measured once as **TradeBalance-derived equity in
`margin_balance_asset`** rather than per-asset wallet balances (2026-07-10 Observation 3); on a
build that has not been probed, treat that as the shape to **check for**, not the shape to expect.
Either way, wallet truth is the Kraken UI or the raw `Balance` endpoint — record which of the two
probe 1 gave you.

If the balance is short, fund it *before* the run, not between probes.

### 1.5 Open-topics / memo sweep

Before an irreversible production action, sweep `docs/open-topics/README.md` and
`docs/memo.local.md` for anything that blocks touching the live account, and present the result with
the go/no-go.

### 1.6 Freeze the pin — decide this first; it can predate everything above

**Stop bumping the pin, and keep it stopped until the engine is armed on the version you pass.**

A nightly channel that moves daily and an arming record matched by exact string are in direct
conflict, and the conflict resolves in exactly one direction — the record does not loosen (§2). So:

- **Freeze before the pass.** The version you run the probes against must be the version that is
  still pinned when the engine is armed. Land the bump you intend to arm on, then stop.
- **Any later bump re-disarms the engine, at the next deploy.** Be precise about when: a bump in the
  repo does not touch a container that is already running, so an engine armed on the old version
  keeps trading on it. What the bump kills is the *path forward* — the armed converge is refused
  from that tree, and once an image built from it is deployed the gate refuses to arm too. Nothing
  warns you at the moment of the bump; the suite stays green by design, and the refusal arrives at
  the arming step, which is the worst moment to discover it.
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

Run from the worktree root (both paths above are relative to it) and pass `--evidence-dir "$EVID"` on every invocation: the evidence default is the cwd, which inside the repo would drop JSONs into git.

The version the harness demands is the one `pyproject.toml` pins, read from the file at every
invocation rather than restated in the script — so the check above and the harness's own refusal
read the same operand, and neither can go stale as the pin moves. It refuses to start against an
interpreter that does not match, and that refusal is the point of the run, never a nuisance to
bypass: clear it with `uv sync`, not with `--expect-nautilus`. (A run from a tree where
`pyproject.toml` is unreadable refuses too, naming `--expect-nautilus` — it will not guess the
string this run is supposed to establish.)

### 2.1 What the record records — settled before the pass, not discovered at it

`cli/engine/order-semantics-verified.json` lists **exact, complete version strings, matched
exactly**. There is no family match, no prefix match, no "rc4 covers all rc4 nightlies". That is a
decision, not an accident of the implementation, and it is not up for revisiting at an arming
window:

- The probes measure **one build**. A prefix that vouched for builds nobody ran would make the
  record say something no attended run ever established, which is the only thing the record is for.
- Both guards already do exact membership and are tested against the near-misses that would
  otherwise slip through — a prefix, a trailing `.post1`, a leading space. Loosening the match means
  weakening both at once, from a file whose entire purpose is to be hard to loosen.
- The cost of exactness is §1.6's freeze. That is the price, it is known, and it is cheaper than a
  guard that vouches for a build nobody measured.

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
what `engine.md`'s pre-probe step 2 is for — converge from the revision the running digest was built
from, and the two operands agree by construction. Reaching for `-e arming_override=...` because
"the record obviously contains it" is the wrong move here; reconcile the tree instead.
Keeping them coincident is `tests/test_nautilus_adapter.py::test_pinned_version`'s job, and it is
why the pin uses PEP 440 arbitrary equality (`===`): the index publishes both `<version>` and
`<version>+<build>` for the same wheel, and `==` matches the local-segment form and orders it above,
so `==` can install a build whose `__version__` is not the string anyone wrote down.

______________________________________________________________________

## 3. Step 0 — prove the harness before pointing it at money

Two checks, both free, both without credentials.

```
$PY $PROBE --selftest
```

**Expect:** every line `ok`, then `SELFTEST PASSED (<n> checks)`, exit 0. This exercises the pure
rails — the notional ceilings, the 25 % distance floor re-measured after quantization, the
quote-freshness and crossed-quote refusals, the client order id collision guard, the leftover
classification that decides whether a run may report "nothing is resting", and the waiting primitive
the whole sequence advances on — and proves each one *bites* on the defect it names. A `FAIL` line
here means **stop**: the rails that bound the money are broken.

```
$PY $PROBE --probes 3 --no-exec --evidence-dir "$EVID"
```

**Expect:** the node starts with a data client only (a warning `No exec_clients configuration found`
is correct here), quotes arrive for all 10 EUR pairs within seconds, probe 3 reports `PASS`, the node
shuts down, exit 0. This is a public-market-data connection: no credentials, no orders, nothing to
lose. It proves the node assembly, the WS path, the callback sequence, the teardown and the exit path
all work before any key is in the shell.

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

**Nonce warning (2026-07-10 Observation 4):** the adapter was measured using finer-than-millisecond
nonces. After any harness run, millisecond-nonce REST scripts on the same key then got
`EAPI:Invalid nonce`. Assume it still holds — any sidecar tooling you reach for afterwards must use
`time_ns()` nonces — since assuming it does costs nothing and assuming it does not costs a debugging
session.

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
| 4b | `filled_qty=0.0` and a terminal status. Which terminal event carries it — `OrderCanceled` (venue-initiated) or an `OrderRejected` naming post-only — is the adapter's mapping and this run's **observation**: either is a pass, and **recording which one you saw is part of the deliverable**. A build not yet probed has no expected answer here; do not carry an earlier build's forward | `filled_qty` > 0 ⇒ post-only protection did not hold. This is an order-semantics failure and per spec 00039 decision 1 it triggers the pre-approved thin-engine fallback. An `OrderRejected` for any *other* reason is not a pass either — the harness scores it FAIL, because the venue never exercised post-only |
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
- A spot buy under `spot_account_type=MARGIN` was measured *not* to show an OpenPositions row —
  the adapter reported margin positions there. On a build that has not been probed that is a thing
  to check and record, not a thing to expect; either way it is not by itself a failure, and probe 5
  is judged on the fill and the flat close. The harness prints this reminder inline.

Record the fee from the fill: 2026-07-10 measured **0.80 %/side** against a modelled 0.6 %, inside
the pre-registered 2× band. A materially different number is a cost-model input (T0014), not an
adapter failure.

### 5.4 Probe 6 — post-run reconciliation, as a fresh process

```
$PY $PROBE --probes 6 --evidence-dir "$EVID"
```

Running it as its **own invocation** is deliberate: the new node's startup reconciliation reads venue
truth rather than the previous process's cache. (Probe 6 also runs in-process at the end of a full
run, but from the cache that run already holds -- it cannot force a fresh venue read, and says so by
marking its own row REVIEW. The separate invocation is the stronger check and the one to quote.)

**Expect:** `open orders 0 (ours 0, other 0), open positions 0`, `PASS`, exit 0.

- `ours` non-zero ⇒ **verdict FAIL**, and the open ids are printed in probe 6's own rows ⇒ go to §8 now. Expect exit **3**, with the cancel-by-hand banner: the final read sweeps every probe-shaped order the venue still holds, including ones this invocation never submitted, so a leftover an earlier run left behind is adopted by startup reconciliation and counted as outstanding. FAIL and the banner read the same cache, so expect the same ids -- but they are read at different moments, and the node holds its clients open for `--order-timeout` seconds after the stop (default 30), so a cancel or fill the venue confirms in that window can legitimately move an id between the two.
- `other` non-zero ⇒ `REVIEW` ⇒ something at the venue is not ours. Adjudicate before signing off.

______________________________________________________________________

## 6. Exit codes

| Code | Meaning | Action |
| -- | -- | -- |
| 0 | every executed probe passed | proceed to §7 |
| 1 | a probe FAILED or errored, **or** a preflight rail refused the invocation before anything started (its message begins `REFUSING:` and no node was built) | read the row; an order-semantics/reconciliation failure (probes 2, 4–6) triggers the pre-approved fallback, anything else is documented and escalated (spec 00039 decision 1) |
| 2 | a probe was refused, **or** the run stopped before its sequence finished | **Read the harness's own output before deciding which of the two this is — they need opposite actions.** A *refusal* (`!! REFUSED before the node was built:`, or a probe row whose verdict is `REFUSED`) submitted nothing for that probe: fix the input and re-run it. A run that *stopped* — an interrupt, an exec client that died, any abnormal exit from the node — may have left a real **open position** that no order read can see, because probe 5's buy filled, its closing sell never ran, and the buy is CLOSED. The harness says so: the `!!` banner `a fill with no closing leg is an OPEN POSITION` and the matching line under *notes requiring a human decision*. Flatten by hand per §8 before re-running anything |
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

**That boundary is normally hours away when you finish**, because §1.2 puts the run at B+35 or later
— so this check is almost always **deferred, not done**, and the write-up happens first. Carry it
across that gap explicitly: give the version's record an **`## Owed checks not discharged by this pass`** section naming the exact boundary (`HH:00 UTC` on the run's date) and what would satisfy it,
then come back at that boundary, take the reading, and **write it into that same section** as its
outcome. The record is the registration; the arming step in [`engine.md`](engine.md) refuses to arm
while any item in it is open, which is what makes the deferral bite instead of evaporating. The same
applies to any reading this section asks for that the run could not take — an `unmatched` delta with
no before-reading, for instance, is an absolute number and not the rise this section wants.

### 7.3 Close the IP exception — mandatory

Kraken → Settings → API → `zcrypto-engine` → edit IP restrictions → **remove the workstation IP**,
restoring the engine host as the key's only allowlisted host (spec 00039 decision 3's closure step).
Do this in the same session as the run. Then close the credential-bearing shell.

### 7.4 Write it up

`kraken-order-semantics-probe.py` prints the table under
`PROBE RESULTS -- paste these rows into docs/reference/adapter-verification/<version>.md`, and writes
`evidence-<stamp>.json` into `--evidence-dir` (default: the cwd) with the full event stream, every planned order, and every
client order id. **Then sweep the homes of "<version> is unverified" in the SAME change**, or the next reader meets a contradiction — the act that satisfies the predicate updates none of the others:

1. **Add the version to `cli/engine/order-semantics-verified.json`**, exactly as the interpreter spells it (§2.1). This clears BOTH guards at once, since they share the file — and it is the act that says the re-run happened, a reviewed diff rather than a memory. Never add a version without the `docs/reference/adapter-verification/<version>.md` doc recording its PASS.
2. **`tests/test_engine_execgate.py`**, which pins the record's exact contents and therefore **FAILS deliberately the moment you do (1)**. That failure is the routing for the rest of this list: its assertion message enumerates the sweep and points back here. Update it deliberately, never by pasting whatever the diff shows.
3. **The arming step in [`engine.md`](engine.md)** — pre-probe step 3, which names the verified version and its record.
4. **The previous version's `docs/reference/adapter-verification/` record**, cross-linked so the series reads as one and neither file claims to be current.

**What is deliberately NOT on this list, and why.** `tests/test_nautilus_adapter.py` used to assert a hardcoded version and go red at every bump; that red was the routing. It no longer does: it now checks only that the installed version equals the version `pyproject.toml` pins, which stays green across bumps and carries no version string to sweep. The pin moves on a nightly cadence, and a test that goes red on every routine move stops being read and starts being repaired — so the routing moved to where it cannot be repaired away:

- **At a bump, nothing goes red, and nothing is supposed to.** The repo sitting on a bumped version while disarmed is the blessed state. The debt is collected at arming, by the converge assert and the runtime gate, each of which blocks the money rather than a test run. §1.6 is what keeps that from ambushing you.
- **At the write-up, item (2) still goes red**, because the thing you just changed is the thing it pins. One deliberate failure, at the one moment a human is already editing the record — which is what a tripwire is for.

Paste the table; keep the JSON in the session scratchpad as the 2026-07-10 run did
("the raw evidence JSONs are preserved in the session scratchpad").

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
3. Only then, re-run `$PY $PROBE --probes 6 --evidence-dir "$EVID"` and confirm `open orders 0 (ours 0 …)`.

Why it matters even though the engine is disarmed: at its next restart the engine's adopt pass reads
every resting order at the venue, finds no ledgered row for a probe order, and **cancels it** — a
silent interaction between two systems, in the logs of only one of them. Leave nothing for it to
find.

**Ctrl-C behaviour:** one Ctrl-C is safe. It reaches two handlers. Nautilus's stops the trader
within a millisecond, which is what runs the harness's cancel-everything sweep — issued while the
exec client is still connected, because the node holds its clients open for `--order-timeout`
seconds after the stop (default 30) precisely so those cancels can reach the venue. The harness's
own handler prints the banner and then swallows every later interrupt, deliberately, so the sweep
always completes. An interrupted run still prints its table and its leftover banner, and exits **2**
— or **3** if anything survived the sweep. If you must abandon it, `kill -9` the process from
another terminal and go straight to §8 by hand.

**What an interrupt does NOT do is finish the run.** Every probe the sequence had not yet reached is
abandoned, the terminal says how many, and their rows never appear — so an interrupted run is never
a partial pass to read verdicts out of. Re-run the probes you still owe, as their own invocation.

**If the interrupt landed after a fill, you may be holding a position.** The closing leg of probe 5
is a submission, and an interrupted run refuses to submit anything further — deliberately, so an
abort cannot open new exposure on the way out, but it means a filled buy has no closing sell. The
harness prints every submitted order with a non-zero fill under a flatten-by-hand banner: go to
Kraken → Trade and flatten before doing anything else, then §8's step 3.

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
and `SOL/BTC`; off by default so the probe-3 row stays comparable with the 2026-07-10 memo), and
`--order-timeout` (default 30 s), which is both how long a probe waits for an accept or a cancel
confirmation **and** the window an interrupted run's cancels have to reach the venue — raise it and
you widen both, so an interrupt costs that much more time before the process exits.
