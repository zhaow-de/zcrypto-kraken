# 00106 — `zcrypto engine flatten`: the red button

Resolves the build half of [[T0159]]. One command, one host wrapper, one runbook section, one widened guard, one verification row — on one branch and one PR, at the Fable review floor (live trade path).

**What it is.** With the engine's kill file written first so nothing can re-open, stop the engine, then against the venue's REST surface: cancel every resting order account-wide, close every margin position with a reduce-only **market** order, sell every non-EUR spot balance at **market** — and report, per leg, what the venue answered. Typed confirmation; `--dry-run` prints the plan and stops; every action journaled; exit codes that distinguish *flat* from *partial* from *could not reach the venue*.

**The ruling it implements (owner, 2026-08-29)**: whole account, market orders, kill file first. And what that overrides: spec `00090` D6 rejected MARKET *as the probe machine's fallback* — "unbounded price on the live path when a bounded marketable limit does the same job". That rejection stands for the probe machine. For this command it is overridden, and the reason is the opposite regime: in a crash the price is not the variable, time is, and a bounded IOC in a fast market leaves residue — and the residue is the exposure.

## The measured basis

Read from the repo on 2026-08-29 at `develop` `77baf605`, and the installed `nautilus_trader 2.0.0rc4.dev20260825`:

| fact | where | consequence |
| --- | --- | --- |
| No code in the repo signs a private Kraken REST call; the only private-side paths are a nautilus `LiveNode` (the engine; the probe harness) | grep `API-Sign\|nonce\|private/` over `cli/` is empty; `infra/scripts/kraken-order-semantics-probe.py` | the command rides the adapter's HTTP client, not hand-rolled signing |
| **One key ⇒ one client**: a second live client on the same key fights the engine over nonces | spec `00090` line 36 | the engine is **stopped** before the command runs — which also removes every race with the engine's own orders |
| `KrakenSpotHttpClient` is stubbed with everything needed and returns `typing.Any` from all of it | `.venv/…/nautilus_trader/adapters/kraken/__init__.pyi` — `request_account_state(account_id, account_type, margin_balance_asset)`, `request_position_status_reports(account_id, instrument_id, account_type, use_spot_position_reports, quote_currency)`, `request_order_status_reports(…, open_only)`, `request_instruments(pairs)`, `submit_order(…, order_type, quantity, time_in_force, …, reduce_only, …, leverage, account_type)`, `cancel_all_orders()` | the *shapes* of what comes back are established only by running against the venue — so the command parses defensively and a live read-only dry-run is part of verification |
| Under `spot_account_type=MARGIN` the account reports **one EUR figure**, not per-asset balances | `docs/reference/adapter-verification/2.0.0rc4.dev20260825.md` observation 2 | spot balances are enumerated with `account_type=CASH`; margin positions with `account_type=MARGIN` — two reads, one client |
| MARKET is live-proven only as a spot GTC order without `reduce_only` or `leverage` (probe 5); `reduce_only` has been placed live only on resting LIMIT closers (probes 4c/4d, `leverage=2`) | the same record; spec `00090` lines 16, 135 | reduce-only MARKET on a margin position is **unverified** until drill B presses the button for real at rung 1; the spec says so rather than pretending |
| A hand-placed kill file on an idle engine cancels nothing until the next restart; the engine has no `on_stop` cancel; `systemctl stop` is `compose down` | `cli/engine/executor.py` `_pickup`/`_pump`; `zcrypto-engine.service:14`; spec `00105` D4 | the command assumes **nothing** was cancelled and sweeps the account itself |
| The exec ledger `exec-<HH>.json` is an unlocked single-writer read-modify-write | `cli/engine/execledger.py:118-122` | the command never writes it; it has its own artifact |
| Every non-zero exit in `cli/` is 1 (`_abort`); no `--dry-run` and no typed confirmation exist in Python; the shell precedent is `converge.sh` reading `/dev/tty` | `cli/engine/command.py:79-89`; `infra/ansible/scripts/converge.sh:41-52` | the exit-code table and the confirm are new conventions, defined here |
| A stopped engine means no container to `docker exec` into | `infra/runbooks/engine.md`'s invocations all `docker exec zcrypto-engine …` | the command runs as a **one-off container** from the same pinned image, through a host wrapper |
| The probe harness never calls `cancel_all_orders` because the production engine shares the account | `kraken-order-semantics-probe.py:49-50` | with the engine stopped, account-wide cancel is exactly right — and only then |

## Decisions

### D1 — One host command, engine stopped first, one-off container

The operator runs **one thing**: `sudo zcrypto-flatten [--dry-run]` on the engine host — a wrapper the engine role deploys to `/usr/local/sbin/zcrypto-flatten` (rendered from `infra/ansible/roles/engine/templates/zcrypto-flatten.sh.j2`, reaching the host on the next attended converge). It does, in order:

1. Writes the kill file — `/var/lib/zcrypto-engine/exec/kill`, one line `<ISO-8601 UTC> flatten`, the engine's own shape (`executor.py:1731`) — **before anything else**. If the engine is running it refuses the next submit and revokes any resting order within a tick; if it is not, the file waits for the next start's adopt pass, which cancels everything at level `none`. The file is a FINDING afterwards, never swept (`engine.md`'s standing rule).
2. `systemctl stop zcrypto-engine` and waits for the unit to be inactive. Spec `00100` measured the drain at ≤ 20 s.
3. `docker run --rm -it --network host --env-file /opt/zcrypto-engine/engine.env -v /var/lib/zcrypto-engine:/var/lib/zcrypto-engine <the image the compose file pins> zcrypto engine flatten "$@"` — the same digest the engine runs, so the verified nautilus version is the one that presses the button; `-it` because the confirm reads the terminal.

`--dry-run` skips steps 1 and 2: it reads the account with the engine **running** (reads only; the nonce cost of a few reads is accepted for a dry run, and the wrapper says so) and prints the plan. The host wrapper is the phone-reachable halt the master plan §10 names, to the extent ssh from a phone is phone-reachable: one command, one word typed.

Rejected: a control file the running engine acts on (`exec/flatten`) — it does nothing when the engine is stopped or wedged, which is when the button is needed. Rejected: a `LiveNode` of its own — startup reconciliation and a data feed are unneeded for a sweep, and the node is the thing that fights over nonces.

### D2 — Transport: the adapter's HTTP client, and nothing hand-rolled

`cli/engine/flatten.py` builds one `KrakenSpotHttpClient(api_key, api_secret)` from `KRAKEN_SPOT_API_KEY` / `KRAKEN_SPOT_API_SECRET` (the env the container already carries; the probe harness's precedent) and uses only: `request_instruments`, `request_order_status_reports(open_only=True)`, `request_position_status_reports(account_type=MARGIN)`, `request_account_state(account_type=CASH)`, `cancel_all_orders`, `submit_order`. Every return is parsed by a small adapter layer with **named fields it requires**; a response missing one aborts **before the first order** with exit 3 and the raw shape journaled — a shape the venue changed is a finding, never something to guess through. The key is a local and a constructor argument: never logged, never in the artifact (`api_key_masked` is what the journal records).

### D3 — Enumeration: what "everything" is

- **Resting orders**: `request_order_status_reports(open_only=True)` — journaled before and after the cancel; the cancel itself is `cancel_all_orders()`, one call, account-wide.
- **Margin positions**: `request_position_status_reports(account_type=MARGIN, use_spot_position_reports=False)` → net signed quantity per instrument; every non-zero row is a leg.
- **Spot balances**: `request_account_state(account_type=CASH)` → free balance per asset; every asset that is not EUR (`EUR`/`ZEUR` — the register's alias rule, `_classify_spot_close`'s `BTC/XBT/XXBT` precedent) with a balance above zero is a leg.
- **Constraints**: `request_instruments(pairs)` for the pairs the legs need — `ordermin`, `lot_step`, `costmin`; sizing reuses `cli/engine/instruments.py::size_order` (floor to `lot_step`, then the `ordermin` and `costmin` floors), the same arithmetic the engine trusts.

### D4 — Order semantics per leg

- **Margin close**: the opposite side, `order_type=MARKET`, `time_in_force=IOC`, `reduce_only=True`, `account_type=MARGIN`, `leverage` = the position report's leverage where it carries one, else **2** — the ratified rung-1 leverage (`00090`, the T2 set) and the only value ever verified live. `reduce_only` is the venue-side bound that this order can only shrink the position; a rejection is journaled and the sweep continues.
- **Spot sell**: `order_type=MARKET`, `time_in_force=IOC`, `account_type=CASH`, `reduce_only=False` (spot cannot carry it — `00090` line 76), quantity = the free balance floored to `lot_step`. Against `<ASSET>/EUR` where the venue lists it; an asset with no EUR pair (the basket's BTC-quoted legs) sells against `<ASSET>/BTC` in pass one, and pass two sells the BTC balance against EUR after balances are re-read.
- **Dust**: a leg whose sized quantity is below `ordermin` or whose notional is below `costmin` is **listed, not sent** — the venue would reject it. Dust does not make the account "not flat": it is below what the venue can trade.
- **Client order ids** are minted with a `FLT-` prefix and never collide with the engine's (`executor.py`'s own-order routing would otherwise treat an ack as its own — the reader's caveat).

### D5 — The sequence, re-runnable

kill file present? (the wrapper wrote it; the command **refuses with exit 1 if it is absent** — the file is load-bearing) → venue `online` via `read_system_status` (30 s bound; not online ⇒ exit 3) → snapshot orders, positions, balances, constraints → print the plan: every leg with side, quantity, pair, the estimate at the taker rate (`docs/reference/kraken-fee-schedule.md`, tier 1 0.80 %), every dust line, every refusal → **`--dry-run` stops here, exit 0** → the confirm: `Type FLATTEN to close every position and sell every non-EUR balance at market, anything else aborts:` read from the controlling terminal, never stdin (converge.sh's rule; no terminal ⇒ exit 1; there is deliberately **no `--yes`** — a red button pressed by a script is a different product) → `cancel_all_orders()`; re-read open orders (a non-empty list is journaled and the sweep continues — the closes do not depend on it) → margin closes, sequentially, each answer journaled, a rejection never retried → re-read positions → spot pass one → re-read balances → spot pass two → final snapshot → exit code. A second run finds less to do and does it; nothing in the sequence is one-shot.

### D6 — Exit codes and the journal

| code | meaning |
| --- | --- |
| **0** | flat: every position closed, every non-EUR balance sold or below the venue minimum (dust listed) — or `--dry-run` completed |
| **1** | refused before the venue was touched: kill file absent, no terminal, confirmation did not match, credentials missing |
| **2** | partial: at least one leg was rejected, unfilled, or came back in a shape the command could not read — the journal names each |
| **3** | the venue could not be reached or read before the first order: `SystemStatus` not `online`, a request failed, a required field absent |

The journal is `/var/lib/zcrypto-engine/exec/flatten-<ISO-8601 UTC>.json` — its own artifact, never `exec-<HH>.json` (D-basis: unlocked single writer): the snapshots before and after, every request with its parameters and every venue answer verbatim, the confirm's outcome, the exit code. The engine's next start reconciles its own ledger against the venue per its adopt rules and reads the kill file as the finding it is; the runbook section says what the operator reads then.

### D7 — The guard widened deliberately, the help text clean

`tests/test_engine_executor.py::test_the_venue_mutating_names_have_exactly_one_module` pins that only `executor.py` names `submit_order`/`cancel_order`. `flatten.py` is a second venue-mutating module **by design** — the guard's allowlist gains it, with the reason in the test's docstring: the engine's machine and the red button must never share code paths, because the button must work when the machine is what broke. `--help` and every printed line carry no internal token (`tests/test_cli_help_hygiene.py` enforces it).

### D8 — Verification before the button is trusted

1. **Unit tests** against a fake HTTP client that records every call and answers from a script: the happy sweep; a rejected margin leg (exit 2, sweep continues); a race fill between snapshot and cancel; dust below `ordermin`; a response missing a required field (exit 3, no order sent); the absent kill file (exit 1, no request); the confirm mismatch (exit 1); `--dry-run` sending nothing. The fake asserts the call **order** of D5.
2. **A live read-only dry-run** on the engine host — attended, the engine running — proves the four read shapes against the real venue and is recorded as a row in `docs/reference/adapter-verification/<version>.md` (the order-semantics runbook's precedent). Until it exists the command's live use is unverified, and the runbook section says so.
3. **Drill B** (`00105` D4) is the end-to-end proof: rung-1 money, a real position from A2, the button pressed, decision-to-flat measured. Reduce-only MARKET on margin is proven there and nowhere earlier; the runbook carries that caveat until the drill-log entry reads `pass`.

## Runbook

`infra/runbooks/engine-procedures.md#engine-flatten` — PROCEDURE, in the file's shape: *What you are seeing* (nothing fired; you are here because the book must be flat within minutes) · *What it means* (what the button does and does not do — it closes positions; it does not clear the kill file, does not restart the engine, does not touch the exec ledger) · *What to do* (`sudo zcrypto-flatten --dry-run`, read the plan; `sudo zcrypto-flatten`, type the word; read the exit code and the journal; then Kraken's own open orders and positions pages by eye; the engine stays stopped and kill-latched until the operator decides otherwise) · *Retire when* (the command no longer exists in `cli/engine/command.py`). Indexed in `infra/runbooks/README.md`.

## Out of scope

- The watchdog-triggered flatten-or-freeze automation the master plan §10 names — this command is the primitive such a watchdog would call; the watchdog is [[T0018]]'s.
- A per-instrument or partial flatten — everything or nothing, by the ruling.
- Cancel-on-stop and re-cancel-on-reconnect — registered in [[T0018]], ruled after drill G.
- Reaching the host from a phone by anything other than ssh.
