# The margin floor reads Kraken's free margin when a plan opening on margin is picked up

Branch `feat/t0230-free-margin-read-at-the-check`, cut from `develop` at `6795cd513` on 2026-11-17, for topic T0230. The owner's order that day, "resolve T0230 in full, then we converge all the fixes in one shot" (D1), puts both of the topic's fixes on this branch: the read at the check and the wording. Its plan is `docs/plans/00162-free-margin-read-at-the-check.md`, reviewed by `zcrypto-plan-review` at tier `full` (`infra/scripts/tier.py --paths` over the plan's files, its output in the plan's head) before its first task.

## Intent and the measured defect

The engine refuses a plan whose margin floor, `sum(notional / leverage)` over its leveraged intents times 2.5 (`cli/engine/probeplan.py:32`, `:220`), exceeds `free_zeur` (`:221-224`). Both callers take `free_zeur` from a balances map under `ZEUR` then `EUR`: the executor's pickup from the Cache's account (`cli/engine/executor.py:2851`, `state.balances` from `venue_state_from_cache`, `cli/engine/venuestate.py:123-126`), and `probe-plan --check` from the newest venue record (`cli/engine/command.py:2188`, `:2198`), which journals the same Cache read at a boundary. The engine's execution client runs the MARGIN account (`cli/engine/node.py:561-562`, `spot_account_type=AccountType.MARGIN`, `margin_balance_asset="ZEUR"`), whose `EUR` row is TradeBalance's free margin, `mf`, read once, at the connect. Measured on the pinned wheel against the loopback (*The measured basis*): the engine's own node read TradeBalance once in a process; with the loopback's `mf` moved from 1387.3 to 1361.3 at a fill, the Cache's `EUR` read 1387.3 to the process's end; the next process read 1361.3. Live under rung 3 the record's `EUR` read 1419.6371 from 2026-11-11 00Z to 12Z across the fills, and 1421.1027 from 16Z, after drill G's restart (`docs/reference/rung3/days.md:73-74`). So the floor is measured against free margin as it stood at the last connect: a plan can pass on margin Kraken no longer has, or be refused on margin it has.

Spec 00090 writes the floor as `sum(notional_i / leverage_i) × 2.5 ≤ free ZEUR balance` (`docs/specs/00090-rung-1-order-path-design.md:68`), the spot wallet's free EUR, where the owner's decision of 2026-09-23 names free margin (`docs/research/14.phase6-decisions.md:841`). No test pins the basis: the one that reads the figure pins the `ZEUR`-then-`EUR` key fallback (`tests/test_engine_executor.py:1834-1849`).

This change reads Kraken's free margin from Kraken when a plan carrying a margin open — a leveraged `open`, the one intent that extends margin — is picked up, one TradeBalance call on the engine's bare REST client; refuses the plan's margin opens alone when that read fails, none of its closes or spot intents; reads nothing for a plan with none, a plan of margin closes among them; and brings spec 00090's floor lines and the probe-window runbook's funding step to free margin.

## Goals, non-goals

Goals:

- The executor measures a plan's margin floor against Kraken's free margin read at the pickup, TradeBalance's `mf` for `ZEUR`, never the Cache's account summary.
- A plan with no margin open reads no free margin and has no floor, rung 3's drafted plans and a plan of margin closes among them, and a plan of margin closes waits for nothing; the floor sums the margin opens alone.
- A read that fails refuses the plan's margin opens, each with a reason naming the failure, and none of its closes or spot intents; nothing falls back to the connect-time figure.
- The basis is pinned by tests in both directions, and a fill between connects moving the figure the check sees is a test of its own.
- Spec 00090's floor lines and the probe-window runbook's funding step say free margin; the reason a refusal journals says free margin.

Non-goals:

- The floor's 2.5 multiplier, and checking it once per plan rather than per intent (D3).
- Refreshing the Cache's account summary, or the venue record's `EUR` (D4, *Out of scope*).
- A live read in `probe-plan --check` (D6).
- The converge: the fleet's concern (D10).

## Constraints

- The engine runs on `zcrypto` and holds the live Kraken trade key; this workstation is the fleet host `zcrypto-ops`. Nothing here reaches Kraken: every reading below is offline, against `tests/kraken_loopback.py`'s loopback, and for the node readings a local `valkey-server` through `tests/cache_restart_child.py`.
- A second client signing on the engine's key is a nonce hazard against the execution client's own signed requests; the engine's bare reads (`_bare_client`, `cli/engine/executor.py:662-675`) run on the terms `read_venue_orders`' docstring states (`:584-598`): with no intent of this process live and no order of it in flight (`_nothing_in_flight`, `:1919-1931`), the residual being the execution client's token request while its socket reconnects.
- A pickup runs on the node's main thread inside the 5-second tick (`on_timer`, `:1451-1494`), and a bare read there blocks the tick up to `_VENUE_READ_TIMEOUT_SECONDS`, 30 s (`:226`).
- `tests/test_internal_terms_not_operator_visible.py` keeps `Phase <N>`, `T<NNNN>`, `iter-<N>`, `spec <NNNNN>`, `D<N>` and `WP<N>` out of the runbook pages and the engine's string literals: the lines and the runbook text below carry none.
- A top-level runbook page's list item with a universal word names its count or declares `(no count command: …)` (`infra/scripts/guidance-guard.py:72-76`); the funding step's text below carries none.
- `.claude/rules/fleet-deploys.md`: the engine converges inside the inter-cycle gap `site.yml` computes, after its preflight, outside a published Kraken maintenance window.

## The measured basis

All read on this workstation on 2026-11-17. The author's, in detached scratch worktrees under `.tmp/t0230/`, both at `6795cd513`: `scratch`, where the first four readings ran on the tree as it stands (the `query_account` one with a scratch hook never in the plan) and the pickup's read with this change applied and committed there; and `base`, the tree as it stands. The plan review's fixes re-took the tests' readings, red and green, and the probes' on a tree of their own, the third fix's standing (*The tests, before and after*), and the CLI's readings are the plan review's. Each tree synced offline (`uv sync --offline --frozen`); `.venv/bin/python -c "import nautilus_trader; print(nautilus_trader.__version__)"` printed `2.0.0rc9.dev20261106`. Every author's run below ran from `.tmp/t0230/scratch` with `TMPDIR` under `.tmp/t0230/tmp`; the measuring scripts sat beside it in `.tmp/t0230/measure/`, which no commit keeps: `tradebalance.py` is pasted here whole, and each other reading is described by its staging and the command line that ran it.

**Which TradeBalance field each bare-client account read reports.** The loopback answering TradeBalance with every field distinct, and BalanceEx with `ZEUR` 1405.2758 and `SOL` 0.05:

```python
"""Which TradeBalance field each bare-client account read reports as EUR, on the pinned wheel, against the loopback."""

import asyncio
import sys

from nautilus_trader.model import AccountId, AccountType

from tests import kraken_loopback

DISTINCT = {"eb": "1500.1", "tb": "1400.2", "m": "12.3", "uv": "4.5", "n": "-0.6", "c": "30.7", "v": "60.8", "e": "1399.6", "mf": "1387.3"}


def main() -> None:
    with kraken_loopback.serve() as venue:
        venue.balances = {"ZEUR": kraken_loopback.balance("1405.2758"), "SOL": kraken_loopback.balance("0.05")}
        forms: list[dict] = []
        plain = venue.answer

        def answer(method, path, query, form):
            if path == "/0/private/TradeBalance":
                venue.private_calls.append("TradeBalance")
                forms.append(dict(form))
                return dict(DISTINCT), []
            return plain(method, path, query, form)

        venue.answer = answer
        account = AccountId("KRAKEN-001")

        def run(label, make):
            venue.private_calls.clear()
            forms.clear()
            client = kraken_loopback.client(venue)
            try:
                async def _read():
                    return await make(client)

                result = asyncio.run(asyncio.wait_for(_read(), timeout=30))
            except Exception as exc:
                print(f"{label}: raised {type(exc).__name__}: {exc}")
                print(f"{label}: private calls {venue.private_calls}")
                return
            print(f"{label}: type {type(result).__name__}")
            balances = getattr(result, "balances", None)
            if balances is not None:
                for b in balances:
                    print(f"{label}: {b.currency.code} total={b.total} locked={b.locked} free={b.free}")
            else:
                print(f"{label}: {result!r}")
            print(f"{label}: private calls {venue.private_calls}")
            print(f"{label}: TradeBalance forms {[{k: v for k, v in f.items() if k != 'nonce'} for f in forms]}")

        run("state MARGIN ZEUR", lambda c: c.request_account_state(account, account_type=AccountType.MARGIN, margin_balance_asset="ZEUR"))
        run("state_with_metrics MARGIN ZEUR", lambda c: c.request_account_state_with_metrics(account, account_type=AccountType.MARGIN, margin_balance_asset="ZEUR"))
        run("margin_metrics ZEUR", lambda c: c.request_margin_metrics(asset="ZEUR"))
        run("margin_metrics None", lambda c: c.request_margin_metrics())
        run("state CASH", lambda c: c.request_account_state(account, account_type=AccountType.CASH))


if __name__ == "__main__":
    sys.exit(main())
```

```
.venv/bin/python ../measure/tradebalance.py
state MARGIN ZEUR: type AccountState
state MARGIN ZEUR: SOL total=0.05000000 SOL locked=0.00000000 SOL free=0.05000000 SOL
state MARGIN ZEUR: EUR total=1399.60000000 EUR locked=12.30000000 EUR free=1387.30000000 EUR
state MARGIN ZEUR: private calls ['BalanceEx', 'TradeBalance']
state MARGIN ZEUR: TradeBalance forms [{'asset': 'ZEUR'}]
state_with_metrics MARGIN ZEUR: type tuple
state_with_metrics MARGIN ZEUR: (AccountState { account_id: "KRAKEN-001", account_type: Margin, base_currency: None, balances: [AccountBalance(total=0.05000000 SOL, locked=0.00000000 SOL, free=0.05000000 SOL), AccountBalance(total=1399.60000000 EUR, locked=12.30000000 EUR, free=1387.30000000 EUR)], margins: [MarginBalance(initial=12.30 EUR, maintenance=0.00 EUR, currency=EUR)], is_reported: true, event_id: UUID4(4d64c715-fc0d-48e7-9744-a91429192ef3), ts_event: UnixNanos(1794936385144731880), ts_init: UnixNanos(1794936385144731880), info: None }, {'equivalent_balance': '1500.1', 'trade_balance': '1400.2', 'used_margin': '12.3', 'unexecuted_value': '4.5', 'unrealized_pnl': '-0.6', 'cost_basis': '30.7', 'valuation': '60.8', 'equity': '1399.6', 'free_margin': '1387.3', 'asset': 'EUR'})
state_with_metrics MARGIN ZEUR: private calls ['BalanceEx', 'TradeBalance']
state_with_metrics MARGIN ZEUR: TradeBalance forms [{'asset': 'ZEUR'}]
margin_metrics ZEUR: type dict
margin_metrics ZEUR: {'equivalent_balance': '1500.1', 'trade_balance': '1400.2', 'used_margin': '12.3', 'unexecuted_value': '4.5', 'unrealized_pnl': '-0.6', 'cost_basis': '30.7', 'valuation': '60.8', 'equity': '1399.6', 'free_margin': '1387.3', 'asset': 'EUR'}
margin_metrics ZEUR: private calls ['TradeBalance']
margin_metrics ZEUR: TradeBalance forms [{'asset': 'ZEUR'}]
margin_metrics None: type dict
margin_metrics None: {'equivalent_balance': '1500.1', 'trade_balance': '1400.2', 'used_margin': '12.3', 'unexecuted_value': '4.5', 'unrealized_pnl': '-0.6', 'cost_basis': '30.7', 'valuation': '60.8', 'equity': '1399.6', 'free_margin': '1387.3', 'asset': 'USD'}
margin_metrics None: private calls ['TradeBalance']
margin_metrics None: TradeBalance forms [{}]
state CASH: type AccountState
state CASH: EUR total=1405.27580000 EUR locked=0.00000000 EUR free=1405.27580000 EUR
state CASH: SOL total=0.05000000 SOL locked=0.00000000 SOL free=0.05000000 SOL
state CASH: private calls ['BalanceEx']
state CASH: TradeBalance forms []
```

On the MARGIN account the `EUR` row is TradeBalance's: `total` the equity `e`, `locked` the used margin `m`, `free` the free margin `mf`, and the BalanceEx `ZEUR` wallet row is gone from it; `free`, what `balances_free()` and so the venue record carry, is `mf`. `request_account_state_with_metrics` is the call `margin_balance_asset` reaches on the execution client (`cli/engine/node.py:565-566`). `request_margin_metrics` asks TradeBalance alone, one private call, and answers `mf` as `free_margin`, a string; it labels the answer by the asset it was asked (`ZEUR` reads `EUR`), and asked none it sends no `asset` and labels the answer `USD`. The CASH read is the spot wallet's free EUR, BalanceEx's, which `read_venue_book` takes (`cli/engine/executor.py:758`) as `VenueBook.eur_free`.

**`request_margin_metrics`' failures.** Against the stock loopback (`eb`, `tb`, `e` and `mf` 1000.0, the rest 0.0): `asset="EUR"` labels `EUR` and `asset="XXBT"` labels `BTC`; Kraken's error `EGeneral:Permission denied` raises `RuntimeError: API error: EGeneral:Permission denied`; a 3 s stall under a 1 s `wait_for` raises `TimeoutError`; an answer without `mf` raises `RuntimeError: Parse error: Failed to deserialize response: missing field `mf` at line 1 column 132`; `mf` of `"NaN"` raises `RuntimeError: Failed to parse TradeBalance 'mf' field "NaN"`; an empty result raises `RuntimeError: Parse error: Failed to deserialize response: missing field `eb` at line 1 column 26` (`.venv/bin/python ../measure/margin_metrics_shapes.py`, each line as printed). At the plan review, the same staging with the loopback's `errors` set to `{"TradeBalance": "EAPI:Invalid nonce"}` and a 30 s `wait_for` printed `raised RuntimeError: API error: EAPI:Invalid nonce` and `after 0.00s, TradeBalance calls 1`: the read's side of a nonce collision is one call and a raise, no retry.

**The connect-time figure on the engine's own node.** `tests/test_cache_restart.py`'s `_Node` and `_venue` over a local `valkey-server` (`Valkey server v=8.1.1`), one spot buy plan dropped (`drop_plan("p-sol-buy", leverage=None, notional_eur=25.0)`), the loopback's TradeBalance answering `mf` 1387.3 (`e` 1399.6) until the AddOrder and `mf` 1361.3 (`e` 1373.6) from then on, the order filled whole by `_script_spot_fills`; then a second process over the venue the first left, TradeBalance answering 1361.3 throughout. The child takes `venue_state_at_start` in the strategy's `on_start` and `venue_state_at_end` at the 14-second window's close (`tests/cache_restart_child.py:294`, `:320`), each by `venue_state_from_cache`:

```
.venv/bin/python -m pytest ../measure/test_connect_figure.py -p no:cacheprovider -q -s --basetemp=/home/zhaow/Projects/zcrypto-kraken/.claude/worktrees/t0230/.tmp/t0230/pt --rootdir=. -c pyproject.toml
process 1: errors []
process 1: venue_state_at_start EUR 1387.3
process 1: venue_state_at_end EUR 1387.3
process 1: TradeBalance calls 1, mf served ['1387.3']
process 1: private calls ['GetWebSocketsToken', 'BalanceEx', 'TradeBalance', 'OpenOrders', 'ClosedOrders', 'TradesHistory', 'OpenPositions', 'OpenPositions', 'BalanceEx', 'OpenPositions', 'AddOrder']
process 2: errors []
process 2: venue_state_at_start EUR 1361.3
process 2: venue_state_at_end EUR 1361.3
process 2: TradeBalance calls 1, mf served ['1361.3']
process 2: private calls ['GetWebSocketsToken', 'BalanceEx', 'TradeBalance', 'OpenOrders', 'ClosedOrders', 'ClosedOrders', 'TradesHistory', 'TradesHistory', 'OpenPositions', 'OpenOrders', 'ClosedOrders', 'ClosedOrders', 'OpenPositions', 'BalanceEx']
fills [{"txid": "OLOOP1-AAAAA-BBBBBB", "side": "buy", "qty": 0.16666666, "price": 150.0}]
process 1 SOL at end None
.
1 passed in 51.57s
```

The figure is read once a process, at the connect, and a fill does not move it; nor does the fill put the bought coin on the account (`SOL at end None`).

**`query_account` through the strategy handle refreshes the Cache's account.** The same staging with a scratch hook at the top of `on_timer`'s `try`, never in the plan — `self._client.query_account(AccountId(_ACCOUNT_ID))` on every tick:

```
process 1: venue_state_at_start EUR 1387.3
process 1: venue_state_at_end EUR 1361.3
process 1: TradeBalance calls 5, mf served ['1387.3', '1387.3', '1361.3', '1361.3', '1361.3']
process 1: private calls ['GetWebSocketsToken', 'BalanceEx', 'TradeBalance', 'OpenOrders', 'ClosedOrders', 'TradesHistory', 'OpenPositions', 'OpenPositions', 'BalanceEx', 'OpenPositions', 'BalanceEx', 'TradeBalance', 'AddOrder', 'BalanceEx', 'TradeBalance', 'BalanceEx', 'TradeBalance', 'BalanceEx', 'TradeBalance']
process 1 SOL at end 0.16666666
1 passed in 51.02s
```

Each query is `BalanceEx` then `TradeBalance` through the execution client's own client, and the Cache's account moves to the answer, coin rows included (`SOL at end 0.16666666`). `query_account` returns nothing to its caller: the answer reaches the Cache as an account event later. The hook was removed (`git checkout -- cli/engine/executor.py`) before anything else ran.

**The pickup's read on the engine's own node, with this change.** A leveraged plan (`drop_plan("p-margin", leverage=2, notional_eur=25.0)`), TradeBalance answering `mf` 1387.3 to its first call and 1361.3 to every later one:

```
.venv/bin/python -m pytest ../measure/test_pickup_read.py -p no:cacheprovider -q -s --basetemp=/home/zhaow/Projects/zcrypto-kraken/.claude/worktrees/t0230/.tmp/t0230/pt --rootdir=. -c pyproject.toml
errors []
venue_state_at_start EUR 1387.3
venue_state_at_end EUR 1387.3
TradeBalance calls 2, mf served ['1387.3', '1361.3']
private calls ['GetWebSocketsToken', 'BalanceEx', 'TradeBalance', 'OpenOrders', 'ClosedOrders', 'TradesHistory', 'OpenPositions', 'OpenPositions', 'BalanceEx', 'TradeBalance', 'OpenPositions', 'AddOrder']
log: 2026-11-17 17:48:46,668 INFO zcrypto.engine.executor [executor.py:2929] - probe plan p-margin: Kraken's free margin reads 1361.30 EUR at its pickup
AddOrder forms 1
.
1 passed in 25.52s
```

The pickup's TradeBalance comes after the startup pass's reads and before the mixed-inventory read's `OpenPositions` and the order; the floor reads 1361.30 while the Cache's `EUR` stays at the connect's 1387.3.

**The tests, before and after.** Scratch readings, re-taken at the plan review's third fix in a detached worktree at `6d0941296`, whose code is `6795cd513`'s, the plan's Task 1 applied from its fences, its test files first and then its code, committed there; each is re-run on the branch by the Task 1 step that lands its code. The test files alone: the executor cases (`-k 'margin_floor_violating or never_the_caches_account or fill_between_connects or free_margin_read_that_fails or held_for_its_plan_alone or spot_only_plan_reads_no_free_margin or walls_refuse_reads_no_free_margin or logs_the_figure or margin_open_waits or read_free_margin or opening_intent_waits'`) read `831 deselected, 19 errors in 4.08s`, each the autouse fixture's `AttributeError: module 'cli.engine.executor' has no attribute 'read_free_margin'`; `tests/test_engine_probeplan.py` reads `1 error in 0.11s`, its import of `extends_margin`; the `--check` case reads `1 failed, 72 deselected in 0.20s`. With the code: `19 passed, 831 deselected in 1.03s`, `64 passed in 0.10s`, `1 passed, 72 deselected in 0.16s`; `tests/test_engine_executor.py -m "not slow"` `850 passed in 5.91s`; `tests/test_engine_stub_fidelity.py` `64 passed in 1.62s`; the union of `infra/scripts/consumers.sh --tests --direct` over the changed code and test files with `tests/test_engine_probeplan.py`, `-m "not slow"`, `3513 passed, 14 skipped, 20 deselected, 4 warnings in 156.41s (0:02:36)`; the restart harness, its slow cases included, `uv run pytest tests/test_cache_restart.py -n 8 -q -p no:cacheprovider --basetemp=.tmp/implementer/pt`, `22 passed in 276.76s (0:04:36)`. The author's first union read three cases red, `tests/test_ops_daily.py::test_the_deploy_log_is_the_main_checkouts_where_a_worktree_runs_the_pass` and `tests/test_prove_inert.py`'s `test_a_tree_it_cannot_list_is_refused` and `test_a_cwd_outside_any_repo_is_a_usage_error_not_a_code_change`, under a `--basetemp` outside the running tree's `.tmp/`; under the plan's `--basetemp=.tmp/implementer/pt` the three read `3 passed in 0.21s` on the branch's tree, `tests/conftest.py:17` setting `GIT_CEILING_DIRECTORIES` to the checkout's `.tmp/`.

**Spec 00090 is not pinned.** `sha256sum docs/specs/00090-rung-1-order-path-design.md` prints `425e724bc60134e175f57cd05fed509be7521eee4db0fb5e4b6947868c6e0104`; `grep -c` of that hash reads `0` in `docs/reference/trial-registry.jsonl` and `0` in `docs/reference/reading-ledger.jsonl`, and of `spec 00090` `0` and `0`. `00090` alone reads `0` and `6`: six digit runs inside the reading ledger's metric arrays, none a spec reference.

**The runbook line that names the floor's source.** `git grep -n -i "free_zeur\|margin floor\|TradeBalance\|free margin\|free ZEUR" -- infra/runbooks infra/grafana docs/reference/fleet.md README.md` prints `README.md:143` alone, `probe-plan --check`'s line, which names the margin floor without its source and stands. A wider read of the probe window finds the source in `infra/runbooks/engine-procedures.md:158`, the pre-probe funding step: "Take the free EUR balance from the venue-truth read … `sum(notional ÷ leverage) × 2.5` over the margin intents must fit under that free balance." Two lines of the same page's rung-2 box procedure lean on that step and on `--check`'s functions, and stand (*Out of scope*).

**`kraken trade-balance --asset ZEUR -o json` on the workstation.** `kraken trade-balance --help` (kraken 0.4.1, local, no request) lists `--asset <ASSET>` defaulting to `ZUSD` and `-o json`. Run once, read-only, by the session running the plan's review at 2026-11-17T18:52:30Z, its JSON carries the keys `cost_basis`, `equity`, `equivalent_balance`, `floating_valuation`, `free_margin`, `free_margin_original`, `margin_amount`, `trade_balance`, `unrealized_pnl` and `unrealized_value`, and no `mf`; `free_margin` read 1420.2187, `equity` 1420.2187 and `margin_amount` 0.0. The figure the funding step names is `free_margin`; with no margin in use, this reading cannot tell it from `equity`, and `free_margin_original`'s value was not recorded. Which key carries TradeBalance's `mf` is read from the binary, not run: `strings -n 6 ~/.cargo/bin/kraken | grep -i free_margin` prints, inside one run of the binary's strings, `ebequivalent_balancetbtrade_balancemargin_amountccost_basisfloating_valuationemffree_marginmluvmfofree_margin_original`, its field table, where `mf` stands before `free_margin` and `mfo` before `free_margin_original`.

**Not measured.** Kraken's own TradeBalance answer for `asset=ZEUR` through the adapter: the loopback answers whatever asset is asked, and the adapter's label is the asked asset's; that the live `EUR` row is free margin rests on this wheel's construction above and the 2026-11-11 figures (`docs/reference/rung3/days.md:73-74`). What Kraken measures a new margin position against, and how `mf` moves with fills, collateral prices and a position's P&L: the one live reading above had no margin in use. Whether Kraken holds or checks free margin against a reduce-only margin close: the floor's sum leaves the closes out on the engine's own classification (`_classify_margin_close`, D3) and the 2026-09-23 basis, not on a reading of Kraken. Which of the CLI's keys carries `mf`: the field table above is read from the binary, not run. TradeBalance's latency at Kraken, bounded by the 30 s timeout. Whether the execution client re-reads the account at a socket reconnect: no reconnect in the node readings; live, the record's figure stood still for twelve hours across the execution socket's roughly hourly drops (`cli/engine/executor.py:127`). What Kraken answers two clients' signed requests out of nonce order, and what the library does when its own token request is the one refused: the loopback reads no nonce, and its `EAPI:Invalid nonce` reading above is the read's side alone. An `mf` of `"inf"`: the floor refuses a non-finite figure whatever the adapter parses.

## Operating model

- **The process.** One engine process, the `zcrypto-engine` container on `zcrypto`, its node running the strategy's callbacks and the 5-second tick on the main thread with no asyncio loop running there. The execution client, KRAKEN-001 on the MARGIN account, reads the account at its connect: `BalanceEx` then `TradeBalance` (`asset=ZEUR`), building the Cache's account, whose `EUR` row is free margin; nothing in the process reads TradeBalance again (*The measured basis*).
- **The shared state.** The Cache's account (`account_for_venue`), read by `venue_state_from_cache` (`cli/engine/venuestate.py:95-128`) into `VenueState.balances` at each pickup and at each boundary's venue record (`cli/engine/cycle.py:507`, `:517`); the venue record, `<journal>/<date>/venue-<HH>.json`, read by `probe-plan --check`; the venue book, `read_venue_book`'s CASH answer (`cli/engine/executor.py:725-795`), the draft's spot balances and `eur_free`, a different figure, the spot wallet's.
- **The bare client.** `_bare_client` builds a `KrakenSpotHttpClient` on the trade credentials per read (`:662-675`); `read_venue_positions` (`:849-872`) is the read beside which the new one sits, one `asyncio.run` under `_VENUE_READ_TIMEOUT_SECONDS`, raising on anything short of an answer.
- **The pickups.** `on_timer` drafts the boundary's plan (`_draft_cycle_plan`, `:3637-3715`) ahead of the drill file's pickup (`_pickup`, `:2756-2790`), each only after the startup pass and with no plan running, and both hand the plan to `_accept_plan` (`:2792-2889`): the kill and reconciliation backstops, the venue truth from the Cache, the wait for a tick with nothing in flight (today, an opening intent under the cache), `plan_refusals`, the mixed-inventory read for an opening intent under the cache (`_mixed_inventory_refusals`, `:2891-2930`), then the journal entry and the file's delete. A drafted plan is spot by construction: `plan_document` writes no `leverage` (`cli/engine/draftplan.py:519-526`), and `ruling_refusals` refuses one on a workstation-drafted plan (`:553-554`); only a drill file the owner places carries a leveraged intent.
- **`probe-plan --check`.** Offline and read-only (`cli/engine/command.py:2151-2220`): the plan, the journal, the newest venue record; its verdict is advisory, the engine re-validating at the pickup.
- **Kraken.** The account's free margin is TradeBalance's `mf`, which the pinned adapter answers as `free_margin` (measured on the loopback). `kraken trade-balance --asset ZEUR -o json` prints a `free_margin`, read once live with no margin in use and then equal to `equity`, and a `free_margin_original`; the binary's field table, read and not run, sets `mf` beside the first and `mfo` beside the second (*The measured basis*). What Kraken measures a new margin position against, and how `mf` moves with fills, collateral prices and a position's P&L, are not measured (*Not measured*). An over-commit, by the 2026-09-23 decision, comes back as a venue rejection: the intent ends `rejected` with no money moved.
- **What identifies the figure and when it is fresh.** TradeBalance's `mf` for asset `ZEUR`, labelled `EUR` by the client. Fresh at its read: today at the process's connect; after this change, also at each pickup of a plan carrying a margin open, the figure that pickup's floor is measured against, logged at INFO.

## Decisions

**D1. The owner's three rulings bind: T0230 was registered on the owner's word, its basis is free margin by the decision of 2026-09-23, and both its fixes ship now on the image that carries T0229's, T0226's and T0227's.** Verbatim, each by its stamp:

- The registration, asked 2026-11-12T11:03:01.042Z by zcrypto-marco, item 7 of its asks: "**7. The EUR finding.** The engine sizes margin refusals from the venue record's `state.balances.EUR`, which read 1421.10. Kraken's actual free EUR was 1405.28. I recommend registering it as a topic, triggered at week 1's close beside T0226, T0227 and T0229." Answered 2026-11-12T11:06:56.778Z: "1a, 5, 6a, 7 as recommended. go for 3." T0230's review corrected the finding's basis (`docs/reference/rung3/days.md:74`): the record's `EUR` is free margin as of the connect, not free EUR.
- The basis, the owner's decision of 2026-09-23, `[T0160]` at `docs/research/14.phase6-decisions.md:839`, its option 2 at `:841`, taken "(owner, 2026-09-23; closed with a comment disposing of each)": "On the MARGIN account the gate reads, EUR `locked` is margin in use, so D2's signal would mean only that a margin position is open and D3 would fire on every pickup while one is; `free_zeur` gates leveraged intents only, free margin the right measure there; an over-commit comes back as a venue rejection, the intent ending `rejected` with no money moved, and Rung 1 is capped at EUR 100 a plan (`exec_max_plan_notional_eur`)."
- The order, 2026-11-17T17:20:42.667Z: "resolve T0230 in full, then we converge all the fixes in one shot".

The basis question `docs/reference/rung3/days.md:74` left for the fix's design, free margin or spec 00090's "free ZEUR balance", is the 2026-09-23 decision's: free margin, gating leveraged intents only (D2, D3, D8); D3 takes it to the intents that extend margin, the margin opens.

**D2. The figure is Kraken's free margin: TradeBalance's `mf` for asset `ZEUR`, labelled `EUR`.** The owner's basis (D1), and the figure the code already reads, as of the connect (*The measured basis*): the same field, read when the check runs. Set aside: the spot wallet's free EUR (BalanceEx's EUR less `hold_trade`, `VenueBook.eur_free`), spec 00090's wording, which counts neither the coins Kraken holds as collateral nor the margin open positions use; the equity `e` or the trade balance `tb`, which do not subtract the margin in use. The asset is one constant, `_MARGIN_BALANCE_ASSET = "ZEUR"` in `cli/engine/node.py`, which `_exec_client_config` passes as `margin_balance_asset` and the new read asks for, so the execution client's summary and the check's read are one figure. Pinned by `test_the_margin_floor_reads_krakens_free_margin_at_the_pickup_and_never_the_caches_account` (both directions: the Cache's `EUR` a million against Kraken's 99.84 refuses; the Cache's 0 against Kraken's 1000 accepts) and `test_read_free_margin_reads_tradebalances_mf_on_the_real_client` (`mf` set apart from `e`, `tb` and `eb`).

**D3. A plan carrying a margin open — an intent with a `leverage` and `action` `open`, the one intent that extends margin — reads free margin at its pickup, in `_accept_plan`, once the pure walls pass and ahead of the mixed-inventory read, and its floor sums the margin opens alone; a plan with none, spot or margin closes alone, reads nothing and has no floor, and a plan of margin closes waits for nothing.** The author's call, on the 2026-09-23 decision's "gates leveraged intents only", taken at the plan review to the intents that extend margin: a margin close is sized from the live position and goes reduce-only (`_classify_margin_close`, `cli/engine/executor.py:1008-1017`), so it cannot open or grow a position, and reading for a plan of closes would cost a signed read and a wait for nothing in flight, for a figure none of its intents is gated by; what Kraken charges a reduce-only close against free margin is not measured (*Not measured*), and the sum's narrowing rests on that classification and the 2026-09-23 basis. A spot close already counts for nothing in the sum (`cli/engine/probeplan.py:200-201`, `:220`). `plan_refusals` keeps the expiry, the future stamp, the duplicate id and the notional cap, and loses the floor; the floor moves to `margin_floor_refusals(plan, *, free_margin_eur)`, which answers nothing for a plan with no margin open whatever the figure, and `extends_margin(plan)` names the test both callers share (`cli/engine/probeplan.py`), the sum filtering on the same per-intent `_extends_margin`. In `_accept_plan`, `if not reasons and extends_margin(plan): reasons, unread = self._margin_floor_refusals(plan)` sits between `plan_refusals` and the mixed-inventory read, the latter's precedent (`if self._cache_enabled and not reasons`, `cli/engine/executor.py:2859`): no signed read for a plan an expiry or a duplicate already refuses. The tick's wait for nothing in flight widens from an opening intent under the cache to a margin open with or without it, the read being signed on the trade key; the plans that wait, two in all: one carrying a margin open, the cache on or off, and under the cache one carrying a spot open, as today; a plan of closes alone, spot or margin, waits for nothing, as today. Its line reads `probe plan <id> waits for a tick with nothing in flight -- it takes a signed venue read`, and the plan's 60-minute expiry refuses a file that waits past it, as today.

What reading costs a spot-only plan: nothing, no call (`test_a_spot_only_plan_reads_no_free_margin[cache-on|cache-off]`, a reader that raises if called); a plan of margin closes the same, no call and no wait (`[margin-close]` of `test_a_margin_open_waits_for_a_tick_with_nothing_in_flight_before_the_free_margin_read_and_a_close_never_does`). Rung 3's drafted plans are spot (*Operating model*), so the loop's boundaries make no new call, and a drafted plan reaches `_accept_plan` with no margin open. What it costs a plan opening on margin: one private call, TradeBalance, synchronous on the tick, up to 30 s on a stall, between the startup pass's reads and the mixed-inventory read (measured on the node). A plan with no margin open was refused today when the Cache's `EUR` read non-finite (`free_zeur is not finite`, `cli/engine/probeplan.py:221-222`); after this change it is not. A plan mixing a margin open with a margin close had its floor sum both; after this change it sums the open alone (`test_the_margin_floor_sums_the_margin_opens_alone`). The floor stays a plan's, checked once at its pickup: free margin moves while a plan's intents run, and an intent that over-commits then is Kraken's refusal, `rejected` with no money moved (D1's decision).

**D4. The read is TradeBalance on the engine's bare client, `request_margin_metrics(asset="ZEUR")`, in a new `read_free_margin` beside `read_venue_positions`.** The author's call, settled by the code and the measurements. `read_free_margin(*, base_url=None) -> float` builds a client by `_bare_client`, runs the one request under `_VENUE_READ_TIMEOUT_SECONDS`, refuses an answer labelled other than `EUR` with an `EngineError`, and returns `float(metrics["free_margin"])`; the executor takes it as `venue_free_margin`, None reading the module's own at call time, as `venue_positions` does. Its nonce terms are the mixed-inventory read's: after the startup pass, with nothing of this process in flight, on the main thread, synchronously, so no other bare read overlaps it; the residual is the execution client's own token request while its socket reconnects, `read_venue_orders`' residual. The read's side of it is measured: a TradeBalance answered `EAPI:Invalid nonce` raises after one call (*The measured basis*), so a collision that refuses the read refuses the plan's margin opens (D5). Which of the two requests Kraken refuses, and what the library does when its token request is the one refused, are not measured (*Not measured*).

Set aside, each with its cost:

| Option | Calls | What it costs |
|---|---|---|
| **TradeBalance on the bare client (taken)** | 1 private | A second client signing on the key at the pickup, on the existing bare reads' terms |
| `request_account_state` on the bare client for the MARGIN account | 2 private, `BalanceEx` and `TradeBalance` | The same figure as `free` (measured), one call more, and an `AccountState` to pick it out of |
| `query_account` through the strategy handle | 2 private per query | No second client: the execution client's own; but the answer lands later as an account event, so the check takes two ticks and a test of the event's arrival; the Cache's account moves mid-run (measured, coin rows included), which the venue record and the library's own pre-trade checks read; and its requests run on the execution client's runtime beside the bare reads the same tick makes after it, the mixed-inventory read's `OpenPositions` among them, the nonce hazard turned round |
| The connect-time figure kept | 0 | The defect |

**D5. A read that fails refuses the plan's margin opens alone, each by its reason naming the failure, and none of the plan's closes or spot intents; nothing falls back to the connect-time figure.** The ruling of the session running the plan's review, verbatim: "a failed free-margin read never refuses a close: what it refuses is the plan's margin opens alone, each journaled `refused` with the read's reason, while the plan's closes and spot intents run — whether by reading at the first margin open's submission or by refusing those intents at the pickup is the fixer's call by the code, the shape that adds the least; the Failure modes' "drop the plan again" is re-trued to it (spec :237)". The shape, the plan review's fix's: the read stays at the pickup, where the floor and its wait are; a failure accepts the plan, the walls passing, with the reason held for the running plan (`_free_margin_unread`, set at every acceptance), and `_start_intent` refuses each margin open by it after the gate's own check, so an intent the gate refuses keeps the gate's reason, through `_refuse_intent` (`cli/engine/executor.py:5188-5194`), the path the gate's and a missing venue truth's refusals of an intent take (`:3046`, `:3053`): journaled `refused` with the reason `Kraken's free margin could not be read for the margin floor -- <class>: <message>`, the WARNING `intent <n> of plan <id> refused: <reason>`. What the pickup refuses, by the read's outcome, three in all: a read that answers and a floor that fits, nothing; a read that answers and a floor that does not fit, the plan whole, its closes with it, the floor being the plan's (D3); a read that fails, the margin opens alone, though under the cache the mixed-inventory check still follows it, and its refusal — its own read failing (`:2904-2909`), or what it reads — refuses the plan whole, closes included, as today (*Out of scope*). Reading at the first margin open's start would move the floor off the pickup and the read off its wait. What raises: a Kraken error (`RuntimeError: API error: …`), the 30 s bound (`TimeoutError`), an `mf` missing or unparseable (`RuntimeError`), an answer labelled other than `EUR` (`EngineError`), missing credentials (`EngineError`, `_bare_client`). Set aside: the connect-time figure as a fallback, the stale figure T0230 is about, used exactly when Kraken cannot be read; refusing the plan whole, which refuses a margin close riding with an open for a figure the close is not gated by, its position left open. The cost: a plan whose margin opens are refused while its closes ran, journaled intent by intent; the operator reads Kraken and drops the margin opens again under a new `plan_id`.

**D6. `probe-plan --check` stays offline and measures the floor against the newest venue record's `EUR`, the engine's free margin as of its last start.** The author's call. The command is "Read-only and offline" by its docstring (`cli/engine/command.py:2164`) and advisory by its help (`:2157-2159`); a live read would sign on the trade key from a second process beside the running engine, outside every in-flight gate the executor holds. It calls `plan_refusals` and `margin_floor_refusals(plan, free_margin_eur=…)` over the same `ZEUR`-then-`EUR` keys, so a plan with no margin open is checked with no floor and one carrying a margin open against the record's figure; its refusal reads `margin floor: <x> EUR required exceeds free margin <y> EUR`. The runbook's funding step says which figure the check reads and where Kraken's own is (D9). Set aside: dropping the floor from the check, which leaves an over-commit to the pickup.

**D7. The read logs one line, INFO with its figure or WARNING with its failure, a refusal its existing WARNING; nothing pages.** The author's call. Each read that answers logs `probe plan <id>: Kraken's free margin reads <x.xx> EUR at its pickup`, so the figure a floor was measured against is in the log whether the plan passed or not; each read that fails logs `probe plan <id>: Kraken's free margin could not be read for the margin floor -- <class>: <message>` at WARNING at the pickup, so the failure is in the log whatever then refuses the plan or ends its margin opens — a later wall such as the mixed-inventory check, a restart or a halt before an open starts; a plan's refusal logs `probe plan <id> refused: <reasons>` at WARNING, and each margin open the failure refuses `intent <n> of plan <id> refused: <reason>` at WARNING; a wait logs `probe plan <id> waits for a tick with nothing in flight -- it takes a signed venue read` at INFO. `zcrypto-engine-error-logs` pages on ERROR and CRITICAL lines of `container="engine"` alone (`infra/grafana/alerts.yaml:616`), so none of the five pages: a plan opening on margin is an attended drill's, its operator reading the plan's entry and the log.

**D8. The wording: spec 00090's floor lines read free margin, amended in place; the code and its reason name free margin.** Spec 00090 is not pinned (*The measured basis*), so CLAUDE.md's immutability does not reach it, and its two statements of the floor's basis are amended where they stand, its D8 and its D13: `≤ free ZEUR balance` becomes `≤ free margin`, D13's pre-probe "confirm free EUR balance covers the plan per D8's floor" becomes "confirm Kraken's free margin covers the plan per D8's floor", and a paragraph headed `**Amended 2026-11-17 (spec 00162 D3 and D8, the owner's decision of 2026-09-23):**` after D8 says what the right-hand side is, which intents the sum runs over, and what the two lines read before, the shape of spec 00086's amendment (`docs/specs/00086-verifiable-dataset-provenance-design.md:74`). In the code `free_zeur` becomes `free_margin_eur`, the reasons `free margin is not finite: …` and `margin floor: … exceeds free margin …`, the multiplier's comment "summed over the margin opens" and "Kraken's free margin" where it read "summed over margin intents" and "the account's free collateral", and `VenueState`'s docstring says `balances` is the execution client's read at its connect, which no fill moves, where it read "had free to spend at `snapshot_at`" (`cli/engine/venuestate.py:56-58`). The basis is pinned by D2's two tests and by `tests/test_engine_probeplan.py`'s exact reasons.

**D9. The probe window's funding step names Kraken's free margin, where to read it, and which figure the check reads.** The author's call: `infra/runbooks/engine-procedures.md`'s `engine-probe-window` pre-probe step 6 (`:158`) has the operator "Take the free EUR balance from the venue-truth read", which after this change is the engine's figure from its last start and not the one the engine measures against. Its text is *Runbook texts*; it names `kraken trade-balance --asset ZEUR -o json` on the workstation and its JSON's `free_margin`, the key the binary's field table sets beside `mf` (*The measured basis*). Step 3's expected `--check` output is unchanged: the check prints no new line.

**D10. The merge ships nothing; the change rides the engine image that carries T0229's, T0226's and T0227's fixes, one converge, the fleet's concern.** The owner's order (D1). *Deployment* says how.

## The answers

What a pickup measures the floor against, by the plan and the read:

| The plan | Today | After this change | Pinned by |
|---|---|---|---|
| No leveraged intent | the floor at 0.0 against the Cache's `EUR`, refused when that reads non-finite | no read, no floor | `test_a_spot_only_plan_reads_no_free_margin`, the cache on and off; `test_a_plan_that_extends_no_margin_has_no_margin_floor` |
| Margin closes alone | their floor against the Cache's `EUR`; nothing waited for | no read, no floor, nothing waited for | `[margin-close]` of `test_a_margin_open_waits_for_a_tick_with_nothing_in_flight_before_the_free_margin_read_and_a_close_never_does`; `test_a_plan_that_extends_no_margin_has_no_margin_floor` |
| A margin open, the walls passing, the read answering | the Cache's `EUR`, free margin as of the connect, the floor summing every leveraged intent | Kraken's `mf` read now, logged at INFO, the floor summing the margin opens alone | `test_the_margin_floor_reads_krakens_free_margin_at_the_pickup_and_never_the_caches_account`, `test_a_fill_between_connects_moves_the_free_margin_the_next_plans_floor_is_measured_against`, `test_the_free_margin_read_logs_the_figure_it_measured_against`, `test_the_margin_floor_sums_the_margin_opens_alone` |
| A margin open, the read failing | — | the failure logged; each margin open refused at its start, the failure its reason, and no close or spot intent by it; the plan accepted unless a later wall refuses it whole, under the cache the mixed-inventory check (*Out of scope*); no later plan's margin open refused by it | `[margin-close]` and `[spot-open]` of `test_a_free_margin_read_that_fails_refuses_the_margin_opens_naming_the_read_and_runs_the_close`, the cache off; `test_a_failed_free_margin_read_is_held_for_its_plan_alone` |
| A margin open, an expiry, a duplicate id or the cap refusing it | refused with the floor's reason beside the others | refused, no read | `test_a_leveraged_plan_the_walls_refuse_reads_no_free_margin`, an expired plan; a duplicate id and the cap feed the same `reasons` its gate reads |
| A margin open, an order of this process in flight | waits when the cache is on; picked up on the tick otherwise | waits for a tick with nothing in flight, the cache on or off | `[margin-open]` of `test_a_margin_open_waits_for_a_tick_with_nothing_in_flight_before_the_free_margin_read_and_a_close_never_does` |

## Tests and guards

New cases, and the existing ones that change:

- `tests/test_engine_probeplan.py`: every `plan_refusals` call loses `free_zeur=`; the five floor cases move to `margin_floor_refusals` and name free margin: `test_the_margin_floor_passes_at_free_margin_100`, `test_the_margin_floor_refuses_at_free_margin_50_naming_free_margin` (`("margin floor: 75.00 EUR required exceeds free margin 50.00 EUR",)`), `test_the_margin_floor_exactly_at_free_margin_passes`, `test_a_non_finite_free_margin_refuses_a_plan_opening_on_margin[nan|inf]`; new `test_the_margin_floor_sums_the_margin_opens_alone` (a spot buy of 90 and a margin close of 30 at 2x beside a margin open of 30 at 2x: `("margin floor: 37.50 EUR required exceeds free margin 37.00 EUR",)`) and `test_a_plan_that_extends_no_margin_has_no_margin_floor` (a spot plan and a plan of one margin close).
- `tests/test_engine_executor.py`: `_VenueFreeMargin`, the `venue_free_margin` reader `_executor` hands every case at 1000 EUR, and the autouse fixture's refusal of the production `read_free_margin`; `test_a_margin_floor_violating_plan_is_refused_naming_the_floor` reads Kraken's 50 EUR; `test_an_eur_only_balance_is_the_free_cash_figure_the_margin_floor_is_measured_against`, which pinned the Cache's key fallback, is replaced by `test_the_margin_floor_reads_krakens_free_margin_at_the_pickup_and_never_the_caches_account[cache-rich-kraken-short|cache-empty-kraken-rich]`; new `test_a_fill_between_connects_moves_the_free_margin_the_next_plans_floor_is_measured_against` (the topic's: one executor, the Cache's `EUR` at 50 throughout, the loopback's `mf` 50 then 1000 between two pickups, the real client reading it, p-1 refused naming 50.00, p-2 accepted, two TradeBalance calls), `test_a_free_margin_read_that_fails_refuses_the_margin_opens_naming_the_read_and_runs_the_close[margin-close|spot-open]` (a margin open beside a margin close on a live position or a spot open, the read raising, the cache off: the plan accepted, the read's failure logged, the open refused naming the read, the intent beside it started), `test_a_failed_free_margin_read_is_held_for_its_plan_alone` (one executor, the first plan's read raising and the second's answering: the second plan's margin open starts), `test_a_spot_only_plan_reads_no_free_margin[cache-on|cache-off]`, `test_a_leveraged_plan_the_walls_refuse_reads_no_free_margin` (an expired plan opening on margin refused for its expiry alone, no read), `test_the_free_margin_read_logs_the_figure_it_measured_against`, `test_a_margin_open_waits_for_a_tick_with_nothing_in_flight_before_the_free_margin_read_and_a_close_never_does[margin-open|margin-close]`, `test_read_free_margin_reads_tradebalances_mf_on_the_real_client`, `test_read_free_margin_raises_on_a_kraken_error_and_past_its_bound[kraken-error|past-its-bound]`, `test_read_free_margin_refuses_an_answer_labelled_other_than_eur`; the existing opening-intent wait case reads the wait's new line.
- `tests/test_engine_command.py`: `test_probe_plan_check_refuses_a_margin_intent_over_the_free_balance`, its venue record's balances `{"EUR": 5.0}`, the one spelling the engine's record carries, reads `margin floor: 50.00 EUR required exceeds free margin 5.00 EUR`.
- `tests/test_engine_stub_fidelity.py`: `_VenueFreeMargin` classified `OURS`.
- `tests/kraken_loopback.py`: `trade_balance`, the TradeBalance answer a test sets, its default today's.
- `tests/cache_restart_child.py`: `read_free_margin` redirected to the loopback and in the pre-build refusal's list, so the harness's margin opens read the loopback; its 22 cases stand.

Each guard is proven by `infra/scripts/mutate-probe.sh --file <file> --control '1,$d' --mutation '<mutation>' -- uv run pytest <test file> -k '<selection>' -q -p no:cacheprovider --basetemp=<…>`, each pattern counting `1` first. The twenty-seven arms below ran in one pass, each pattern counting `1`, on the scratch commit *The tests, before and after* names, and each read `mutate-probe: KILLED (control proven, tree restored byte-identically)`: a scratch reading, which Task 1's Step 7 re-runs on the branch, its probes file the proof.

| Guard | Test file, `-k` | File and mutation |
|---|---|---|
| The floor refuses above free margin | `test_engine_probeplan.py`, `refuses_at_free_margin_50` | `cli/engine/probeplan.py`, `s/    if margin_required > free_margin_eur:/    if False:/` |
| Its reason names free margin | the same | `s/exceeds free margin {free_margin_eur:.2f} EUR/exceeds free_zeur {free_margin_eur:.2f} EUR/` |
| The boundary itself passes | `exactly_at_free_margin` | `s/    if margin_required > free_margin_eur:/    if margin_required >= free_margin_eur:/` |
| No floor without a margin open | `extends_no_margin_has_no_margin_floor` | `s/    if not extends_margin(plan):/    if False:/` |
| A close extends no margin | the same | `s/return intent.leverage is not None and intent.action == "open"/return intent.leverage is not None/` |
| A non-finite figure refuses | `non_finite_free_margin` | `s/    if not math.isfinite(free_margin_eur):/    if False:/` |
| The floor sums the margin opens alone | `sums_the_margin_opens_alone` | `s/for i in plan.intents if _extends_margin(i))/for i in plan.intents if i.leverage is not None)/` |
| The basis: Kraken's read, never the Cache's | `test_engine_executor.py`, `never_the_caches_account` | `cli/engine/executor.py`, `s/free = (self._venue_free_margin or read_free_margin)()/free = venue_state_from_cache(self._cache, clock=self._now).balances.get("EUR", 0.0)/` |
| A spot-only plan reads nothing | `spot_only_plan_reads_no_free_margin` | `s/if not reasons and extends_margin(plan):/if not reasons:/` |
| A plan the walls refuse reads nothing | `walls_refuse_reads_no_free_margin` | `s/if not reasons and extends_margin(plan):/if extends_margin(plan):/` |
| A plan of margin closes reads nothing | `margin_open_waits` | `s/if not reasons and extends_margin(plan):/if not reasons and any(i.leverage is not None for i in plan.intents):/` |
| A failed read is caught | `free_margin_read_that_fails` | `/def _margin_floor_refusals/,/def _mixed_inventory_refusals/s/except Exception as exc:/except ZeroDivisionError as exc:/` |
| A failed read refuses the margin opens | the same | `s/if self._free_margin_unread is not None and _extends_margin(intent):/if False:/` |
| A failed read runs the close | the same | `s/if self._free_margin_unread is not None and _extends_margin(intent):/if self._free_margin_unread is not None:/` |
| A failed read runs the spot intents | the same | `s/if self._free_margin_unread is not None and _extends_margin(intent):/if self._free_margin_unread is not None and intent.action == "open":/` |
| A failed read is logged when it fails | the same | `/logger.warning("probe plan %s: %s", plan.plan_id, unread)/d` |
| A failed read is held for its plan alone | `held_for_its_plan_alone` | `s/self._free_margin_unread = unread/self._free_margin_unread = unread or self._free_margin_unread/` |
| Each pickup reads again | `fill_between_connects` | `s/free = (self._venue_free_margin or read_free_margin)()/free = self.__dict__.setdefault("_free_once", (self._venue_free_margin or read_free_margin)())/` |
| The read is `mf` | `reads_tradebalances_mf` | `s/return float(metrics\["free_margin"\])/return float(metrics["equity"])/` |
| It asks for `ZEUR` | `reads_tradebalances_mf` | `s/request_margin_metrics(asset=_MARGIN_BALANCE_ASSET)/request_margin_metrics()/` |
| An answer not in EUR is refused | `labelled_other_than_eur` | `s/    if asset != "EUR":/    if False:/` |
| The read is bounded | `read_free_margin and past_its_bound` | `s/metrics = asyncio.run(asyncio.wait_for(_read(), timeout=_VENUE_READ_TIMEOUT_SECONDS))/metrics = asyncio.run(_read())/` |
| A margin open waits for nothing in flight | `margin_open_waits` | `s/reads_venue = extends_margin(plan) or (/reads_venue = (/` |
| A plan of margin closes waits for nothing | `margin_open_waits` | `s/reads_venue = extends_margin(plan) or (/reads_venue = any(i.leverage is not None for i in plan.intents) or (/` |
| The INFO line carries the figure | `logs_the_figure` | `/free margin reads %.2f EUR at its pickup/d` |
| `--check` measures the floor | `test_engine_command.py`, `margin_intent_over_the_free_balance` | `cli/engine/command.py`, `/\*margin_floor_refusals(plan, free_margin_eur=float(free_margin)),/d` |
| `--check` reads the record's `EUR` | the same | `s/ or balances.get("EUR", 0.0)//` |

No arm selects a `slow` case: the child's redirect is held by the harness's existing cases, whose margin opens would otherwise reach `_loopback_bare_client`'s refusal and record an error.

Two backstops Task 1 adds take no arm, an explicit drop: `_no_production_venue_read`'s refusal of the production `read_free_margin`, and `read_free_margin`'s entry in `tests/cache_restart_child.py`'s `_refuse_production_defaults`. Each fails a run that reaches the production read off the loopback, and no case is built to: `_executor` hands every case a reader, the loopback cases pass their `base_url`, and the child's redirect carries one; so no `-k` selection moves the fixture's, and the child's would move only through the slow harness.

## Change list

- `cli/engine/probeplan.py`: `_extends_margin` and `extends_margin`; `plan_refusals` without the floor or `free_zeur`, its docstring and the cap's comment; `margin_floor_refusals`; the multiplier's comment.
- `cli/engine/executor.py`: the import; `read_free_margin`; `ProbeExecutor`'s `venue_free_margin` and its docstring line; `_nothing_in_flight`'s docstring; `_accept_plan`'s widened wait, its comment and line, and the floor's call in place of `free_zeur`; `_margin_floor_refusals`; `_free_margin_unread`, set at each acceptance, and `_start_intent`'s refusal of a margin open by it.
- `cli/engine/node.py`: `_MARGIN_BALANCE_ASSET`, passed as `margin_balance_asset`.
- `cli/engine/command.py`: the import; `probe-plan --check`'s floor through `margin_floor_refusals`, and its comment.
- `cli/engine/venuestate.py`: `VenueState`'s docstring.
- `cli/engine/flatten.py`: `QUOTE_CURRENCY`'s comment, whose "`ZEUR` reaches the venue raw only through the exec client's `margin_balance_asset`" the new read makes false; it names TradeBalance's `asset`, `_MARGIN_BALANCE_ASSET`.
- `tests/test_engine_probeplan.py`, `tests/test_engine_executor.py`, `tests/test_engine_command.py`, `tests/test_engine_stub_fidelity.py`, `tests/kraken_loopback.py`, `tests/cache_restart_child.py`: *Tests and guards*.
- `docs/specs/00090-rung-1-order-path-design.md`: D8's floor line, D13's pre-probe funding line, and the amendment after D8 (D8).
- `infra/runbooks/engine-procedures.md`: the probe window's pre-probe step 6 (*Runbook texts*).
- `docs/research/14.phase6-decisions.md`: the `[00162]` entries.
- `docs/open-topics/T0230-the-margin-floor-reads-a-free-margin-figure-refreshed-only-at-connect.md`: resolved and moved to `docs/open-topics/archive/`; `docs/open-topics/README.md` re-rendered.

## Runbook texts

In `infra/runbooks/engine-procedures.md`, `## engine-probe-window — PROCEDURE`, `#### 1. Pre-probe — before anything touches the host`, item 6 reads in whole:

```markdown
6. **Confirm funding covers the plan, by hand, before the tooling does it for you.** The margin floor is measured against Kraken's free margin, which `kraken trade-balance --asset ZEUR -o json` on the workstation prints as `free_margin`. The engine reads Kraken's free margin when it picks up a plan that opens on margin: a floor that does not fit refuses the plan whole, its closes with it; a read that fails refuses the plan's margin opens alone and runs its closes and spot intents, unless the engine's cache is on and the mixed-inventory check that follows the read refuses, its own margin-positions read failing among its reasons: that refuses the plan whole, its closes with it. So a close that must run goes in a plan of its own. A plan with no margin open, spot or closes alone, reads nothing and has no floor. The venue-truth read's `EUR` balance is Kraken's free margin as the engine read it at its last start, which no fill moves, and `probe-plan --check` measures the floor against that one, so the check can pass on margin Kraken no longer has. The plan's total `notional_eur` must be at or under `exec_max_plan_notional_eur` in `/opt/zcrypto-engine/zcrypto.toml`, and `sum(notional ÷ leverage) × 2.5` over the margin opens, the intents with a `leverage` and `"action": "open"`, must fit under Kraken's free margin. `probe-plan --check` recomputes both below and refuses on either — this step is so you learn it before the window, not during it.
```

The text went through the repository's hooks on the scratch tree *The tests, before and after* names (`mdformat` left the page unchanged), `infra/scripts/guidance-guard.py --uncounted infra/runbooks/engine-procedures.md` printed no line before or after it, and `tests/test_internal_terms_not_operator_visible.py` passed over it.

## Deployment

The merge ships nothing: the engine runs the image its pin row names until a converge re-pins it. The spec 00090 amendment and the runbook step land at the merge; the step is true of the new image, and on the image running until the converge its "The engine reads Kraken's free margin when it picks up a plan that opens on margin" is not yet so, which matters only to a plan opening on margin placed in that span, none being scheduled (rung 3 is spot). This change rides the engine image built from `develop` once T0229's, T0226's and T0227's fixes and this one are merged, and one engine converge takes them (D10). That converge is the fleet's concern under `.claude/rules/fleet-deploys.md` and `.claude/skills/zcrypto-rollout-image/SKILL.md`: inside the 4-hourly inter-cycle gap `site.yml` computes from the boundary cycle's journalled completion, after the candidate image's own `zcrypto engine preflight` passes on the engine host, with Kraken's scheduled-maintenance feed read whole at planning and again immediately before, `--tags engine` with `-e converge_primary=true`.

What shows the change on the real engine is the first plan opening on margin picked up on the new image: its INFO line `probe plan <id>: Kraken's free margin reads <x> EUR at its pickup`, read against the `free_margin` of `kraken trade-balance --asset ZEUR -o json` taken beside it. Rung 3's boundaries show nothing new: their plans read nothing.

## Failure modes

- **The read fails** — a Kraken error, the 30 s bound, an unparseable answer, an answer not in EUR, missing credentials. The failure is logged at WARNING at the pickup; the plan is accepted, the other walls passing, the file deleted, and each margin open is refused at its start with the failure as its reason, journaled, its WARNING logged; no margin open's order goes, and none of the plan's closes or spot intents is refused by it. Under the cache the mixed-inventory check follows, and its refusal — an outage that fails its read too, or what it reads — refuses the plan whole, its closes with it. The operator reads Kraken and drops the margin opens again under a new `plan_id`; a close a whole refusal held back goes in a plan of its own.
- **The read collides with the execution client's own signed request** — its token request while its socket reconnects, the residual `read_venue_orders`' docstring names. A read answered `Invalid nonce` raises after one call (measured on the loopback): the first mode. Under the cache the mixed-inventory check's own signed read follows it on the same tick, a second request inside the same reconnect window. Which request Kraken refuses, and what the library does when its token request is the refused one, are unmeasured.
- **The read stalls.** The tick blocks up to 30 s on the main thread for the read; under the cache the mixed-inventory check's signed read follows it on the same tick, whether the read answered or failed, a floor that does not fit aside, so a stall that holds both blocks the tick up to 60 s; no plan is running at a pickup and nothing of this process is in flight, so no order is polled late, but the gate's idle refresh and the socket watchdog's tick wait with it, as on the other bare reads.
- **An order of this process stays in flight.** A plan opening on margin waits in its file, tick after tick, until it clears; past 60 minutes from `created_at` the expiry refuses the file. A plan of margin closes waits for nothing.
- **Free margin moves after the read.** The floor is the plan's, checked once at the pickup; an intent that over-commits as the plan runs comes back, by the 2026-09-23 decision, as Kraken's rejection, `rejected` with no money moved, the plan's notional capped at `exec_max_plan_notional_eur`.
- **A non-finite figure.** The adapter refuses `NaN` at its parse (measured), and the floor refuses a non-finite figure whatever reaches it.

## Open questions for the owner

None open. The choice of read, D4, is settled by the measurements: of the two that read the figure now, the bare-client TradeBalance is one call on the bare reads' existing terms, and `query_account` costs an asynchronous two-tick check, a mid-run change to the Cache's account and a race against the bare reads that follow it; the failure's handling, D5, is the plan review's ruling.

## Out of scope

- The venue record's `EUR`, which stays the connect-time figure: after this change no engine decision reads it, `probe-plan --check`'s advisory floor aside (D6), and the daily read compares Kraken's own (`docs/reference/rung3/days.md`).
- Refreshing the Cache's account mid-run (`query_account`, D4): set aside for its costs; the library's own pre-trade checks keep reading the connect-time account, as today.
- The floor's multiplier and its once-a-plan check (D3).
- A restart-harness case for the pickup's read: dropped, since `test_a_fill_between_connects_moves_the_free_margin_the_next_plans_floor_is_measured_against` drives the real client through the executor and *The measured basis* pastes the node's reading; the harness's existing margin opens hold the child's redirect.
- `README.md:143`'s `probe-plan --check` line, which names the margin floor without its figure and stays true.
- Two lines of `infra/runbooks/engine-procedures.md`'s `engine-rung-2-box` procedure: `:477`, whose "step 6's free EUR" points into the funding step this change rewrites, and `:446`, whose pointer names `_intent_floor_check` and `plan_refusals` as `--check`'s two checks, `margin_floor_refusals` now a third. The box is over: its *Retire when*, the exit report recorded, is met (`[00092] Rung 2's exit report` in `docs/research/14.phase6-decisions.md`), so no window runs either line, and the box's plans carried no `leverage` (`:440`).
- A floor that does not fit refuses the plan whole, a margin close in it included: the floor is the plan's (D3), now summed over the margin opens alone, so it refuses less than before. Not behaviour this change introduces, and rung 3's plans carry no leverage; ruled as today by the session running the plan's review, the owner told, theirs to overturn.
- Under the cache, a refusal by the mixed-inventory check — its margin-positions read failing, or what it reads — refuses the plan whole, closes included, a plan whose free-margin read failed among them (`cli/engine/executor.py:2891-2930`). Not behaviour this change introduces, and rung 3's plans carry no leverage; ruled as today by the same session, the owner told, theirs to overturn.
