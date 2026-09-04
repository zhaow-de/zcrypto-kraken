---
status: open
ripe_when: 'per sub-item. Bump: the engine row of `docs/reference/fleet-pins.md` names 00106 and rest-hold, AND a `docs/reference/adapter-verification/` row records `zcrypto engine flatten` run once on the pin in `pyproject.toml`. Cancel sweep and adopt pass: `grep nautilus-trader pyproject.toml` no longer reads `2.0.0rc4.dev20260825`, which owes the reading in this file against the new wheel, OR an attended engine start on the live account is planned with an order resting at the venue that the starting process did not place, on one of BTC/EUR, ETH/EUR, XRP/EUR, LTC/EUR, ETH/BTC'
---

# T0160 — nautilus-trader nightly bump, and the flatten contract checks it must not skip

## Context — what

The repo pins `nautilus-trader===2.0.0rc4.dev20260825` (`pyproject.toml`, index `nautechsystems`). On 2026-08-31 a scan of `nautechsystems/nautilus_trader` counted **154 commits merged since that nightly**. Three of them touch surfaces `cli/engine/flatten.py` depends on, and one of those is a latent behaviour change that would make the flatten command refuse to run rather than fail loudly.

The bump itself is trivial. This topic exists because the **checks that must ride with it** are not, and they are not derivable from the diff — they come from knowing which upstream changes intersect this repo's read path.

**It now holds a second subject, which the bump does not own.** The same adapter's order-report read drops an order whose pair its instrument cache cannot resolve — silently, with a successful empty return — and that blinds the engine's kill-switch cancel sweep **and its startup adopt pass** on five basket legs. The repair is parked pending the v2 release rather than absent, and it is registered as a sub-item below because a deferral whose only home is a PR body or an unmerged branch's prose is untracked.

**What the defect makes false has been corrected on the surfaces a reader acts on**, and the list is the useful part: the flatten command's reads, verdict, `--help` and README row and its runbook procedure; the kill-switch trip and the startup adopt pass in code; the probe window's restart step and the order-path drills that turn on that pass, including which pair their plan may name; the go/no-go harness's post-run count and its runbook; and the external-events counter's help text and dashboard panel. **Point-in-time records deliberately keep their original wording** — `docs/reference/adapter-verification/`, archived topics, and committed specs and plans. What remains here is the repair itself.

## Why this matters

`zcrypto engine flatten` submits market orders against the live account. Its reads are deliberately defensive: `_required(obj, field, what)` raises `FlattenUnreachable` when a named field is absent or `None`, and that abort is correct **before** the first write because aborting is free there. That same strictness turns an upstream `Some/None` change into a refusal to flatten.

A bump that lands green on the unit suite therefore proves very little about this command: the whole reason the async defect below survived ten tasks and ~1900 green tests is that the test doubles were written to match our code rather than the venue.

## The bump is not cheap — it disarms trading until an attended live-money pass re-earns it

**This is the constraint that governs sequencing, and it is mechanical, not advisory.**

`cli/engine/order-semantics-verified.json` lists the nautilus versions whose attended ~EUR 0.20 order-semantics pass has actually happened. **Two independent guards read that one file:**

- `cli/engine/execgate.py` refuses the gate at runtime when the RUNNING interpreter's `nautilus_trader` is absent from the list.
- `infra/ansible/roles/engine/tasks/main.yml` refuses a converge rendering `exec_armed=true` on a version absent from the list.

The file's own note is explicit: *"The pin is FROZEN at this string until the engine is armed on it"*, and *"Never add a version without the `docs/reference/adapter-verification/<version>.md` record that carries its PASS."*

So bumping off `2.0.0rc4.dev20260825` **cannot** be a lockfile edit followed by a converge. Until a new attended six-probe pass runs against the new version on the live account and its record is committed, the engine cannot arm — and a converge that renders `exec_armed=true` is refused by the role. \[\[T0085\]\] holds that pass as one of its three legs and records the last one (2026-08-26, PASS on all six probes, EUR 0.16).

**Consequence for planning:** the bump belongs *with* its order-semantics pass, not before it, and neither belongs in a converge window shared with unrelated residuals.

**What sits behind the bump leg's trigger.** The upstream PR this topic waited on merged 2026-09-01 (`904862a8`), so the bump is live work rather than a watch. Its two conditions are ordering rather than ceremony: the engine converged onto `00106` + rest-hold, and `zcrypto engine flatten` watched to succeed once on the CURRENT pin — that baseline is what makes the side-enum hazard below attributable to the bump rather than latent. The bump shares a window with neither.

## Findings so far

Measured 2026-08-31 against the pinned version, in the `feat/00106-engine-flatten` worktree.

**The three upstream commits that intersect this repo:**

- **`Preserve Kraken Spot request correlation after timeouts`** — "Retain request state until definitive evidence or shutdown", "Send submit and batch compensating cancels without rejection", "Reset timeout cancellation state across reconnects", "Document unknown outcomes and recovery behavior". This is squarely on the flatten write path: a lost request correlation after a timeout is the "did my order go out?" case the incident journal exists to record. This is the bump's main prize, not a risk.
- **`Refine model side enums`** — "Make core side enums fully specified and remove duplicate types", "**Use `Option` for missing sides across model and adapter boundaries**", "Preserve legacy `NO_*` aliases in Python, serde, and the C ABI". The middle bullet is the hazard; the third is the reason it may be a non-issue.
- **`Standardize adapter task lifecycles`** — may move the async surface that `cli/engine/flatten.py` was corrected against (see below).

**The pinned version's behaviour, measured, so the bump has a baseline to differ from:**

- Every `KrakenSpotHttpClient.request_*` raises `RuntimeError: no running event loop` when called outside a loop; inside one it returns a `Future` whose await yields the value.
- `inspect.iscoroutinefunction` returns **`False`** for all seven of `request_instruments`, `request_book_snapshot`, `request_position_status_reports`, `request_account_state`, `request_order_status_reports`, `submit_order`, `cancel_all_orders`. It is not authoritative over these pyo3-backed methods — **do not use it to judge whether the bump changed async-ness; call the method and look at what comes back.**
- `OrderBook.bids` and `OrderBook.asks` are `method_descriptor` — methods, not attributes.

### The order-report read's instrument lookup, and the four engine-path readings around it

Measured 2026-09-03 against the pinned wheel, on a real `LiveNode` and against a loopback venue. **These readings were taken on the parked flatten-cache branch and are not re-checkable from `develop` alone** — the two live arms need the trade credential, and the wheel ships as one stripped compiled extension (`nautilus_trader/_libnautilus.cpython-314-x86_64-linux-gnu.so`), so no source read on this machine settles them either.

**The mechanism.** The Kraken spot HTTP client's instrument cache is keyed on the instrument id and scanned by `raw_symbol`, which is Kraken's `AssetPairs` **key** (`XXBTZEUR`); an open order is looked up by its own `descr.pair`, which is the **altname** (`XBTEUR`). The comparison is raw equality inside an `if let Some(...)` with no `else`, so an unresolved row is dropped with no warning and the call returns a successful, short list. **Five of the twelve `BASKET` legs are spelled both ways — BTC/EUR, ETH/EUR, XRP/EUR, LTC/EUR, ETH/BTC** — and that set is recomputable from repo state alone, from `cli/engine/store.py`'s `PAIR_KEYS` against `cli/backfill/read.py`'s `dump_pair_name` (`tests/test_engine_flatten.py::test_the_blind_legs_are_the_two_way_spelled_basket_legs` is that computation).

The four readings that decide what a repair may and may not assume:

1. **There is no local door, and both candidates are PROVEN CLOSED** — positively established, not merely unfound. No execution-client object exists in Python to hook: the factory's public surface is exactly `['name']`, a depth-4 walk of a built node found nothing exposing `cache_instrument`, and interposition was refused four ways. And the node's own instrument path is closed by a controlled A/B on a real `LiveNode` against **two loopback venues, one per client**: an instrument present in the data client's listing and absent from the exec client's own gives `Received 0 order(s)`, while the control arm gives `external=1, open=1`. Timing was ruled out by a 70–400 ms spread.
2. **The exec client's cache is populated KEY-ONLY, not cold.** It fetches its own `/0/public/AssetPairs` and logs `Loaded 2856 Spot instruments`. So the hazard is **spelling**, not population — and the stacked worry that "an empty adopted set is indistinguishable from a spelling miss" can be struck: the set is never empty for want of population.
3. **Flatten's twin shape is INVERTED for the engine, and this is the most expensive thing here to assume.** A **distinct-id** twin — the shape flatten's own cache priming *requires* — is parsed and then dropped by the execution manager (`WARN: 1 orders skipped (instrument not in cache)`, Cache empty). A **same-id alias** reconciles fully. **A plan that says "do for the engine what flatten does" ships an inert fix.**
4. **An altname-spelled open POSITION aborts startup loudly** — `RuntimeError: Failed to get mass status from KRAKEN`, exit 1 — rather than dropping silently. The order read is the asymmetric one; the position read fails closed.

**And the executions subscription is sent with `snap_orders:false, snap_trades:false`** — measured on this build. So "the WS execution stream delivers changes, not a snapshot" is no longer an inference corroborated by `_adopt_resting_orders` existing at all: a pre-existing resting order receives no WS event and therefore never self-heals into the Cache by any route other than the reconciliation read. That closes the one link in the argument below that was previously reasoning rather than measurement.

## Suggested next steps

### The bump's own contract checks

Do these **on the bump branch, before merging it** — each one names what to run and what result means "safe".

- **Bump and lock.** Edit the pin in `pyproject.toml` to the chosen nightly, `uv lock`, `uv sync`. Per `CLAUDE.md` a `uv.lock` / `pyproject.toml` change reaches everything, so this branch takes the **full local suite**, not a reachable subset.
- **Check the side-enum change against `position_side`, first and before anything else.** Run a real `request_position_status_reports` against the account (reads only) with at least one open margin position and at least one flat/closed row, and print `repr(row.position_side)` for every row. **Safe result:** flat rows still carry a `FLAT`-like sentinel that `str()`s to `"FLAT"`. **Hazard result:** any row reports `position_side is None` — then `_required(row, "position_side", …)` raises `FlattenUnreachable` and `run_flatten` exits 3, i.e. the command **refuses to flatten an account** instead of skipping that row. If the hazard result appears, fix `cli/engine/flatten.py`'s flat-row handling in the same PR; do not merge the bump alone.
- **Re-measure the async surface** exactly as recorded under *Findings so far*: call `request_instruments()` outside a loop (expect a raise) and inside one (expect an awaitable). If `Standardize adapter task lifecycles` changed either, `cli/engine/flatten.py`'s `Recorder.call` and the `asyncio.run` boundary in `cli/engine/command.py` need revisiting together.
- **Re-measure `OrderBook.bids` / `.asks` kind.** `getattr(OrderBook, "bids")` must still be callable; `read_book_price` calls `book.bids()`. If they became properties, that call inverts.
- **Re-run the flatten contract pin** added with the async correction (the env-gated one) and say in the PR what it proved and what it did not.
- **Read the Kraken correlation fix's own tests** to learn what "unknown outcome" the adapter now reports, and check whether `cli/engine/flatten.py`'s `post_write_failure` / exit-2 path should record it distinctly rather than as a generic transport failure.
- **Scan the remaining ~150 commit headers for adapter- and model-level changes** not covered above (`gh api "repos/nautechsystems/nautilus_trader/commits?since=<pinned nightly date>T00:00:00Z&per_page=100" --paginate --jq '.[] | .commit.message | split("\n")[0]'`), and record any new intersection in this file before closing it.

### The kill switch's cancel sweep and the startup adopt pass are blind on five legs — only their repair is left here

**Not a bump-branch check, and not a documentation item.** The false claims have been corrected as `## Context — what` lists; what is registered here is the capability the engine does not have.

- **The engine cannot cancel a resting order it did not place, on a two-way-spelled leg.** `cli/engine/node.py`'s `_exec_engine_config()` sets `reconciliation=True` and `filter_unclaimed_external_orders=False`, and that second line exists precisely so a previous process's or a hand-placed order reaches the Cache instead of being filtered out of it. It is necessary and not sufficient: such an order reaches the Cache **only** through startup reconciliation, which obtains order state through the order-report read the mechanism above describes — and with the executions subscription carrying `snap_orders:false`, no WS event ever heals the gap afterwards. Two consumers read that Cache through `self._client.cache.orders_open(venue=_VENUE)`, counted against `develop`: `executor._adopt_resting_orders`, the startup adoption pass, and `executor._cancel_resting`, whose own docstring opens *"A trip must leave NOTHING working at the venue"*. `_cancel_resting` issues `cancel_order` **per order** off that list, so an order the list omits is **never requested at all** — a capability gap, not a failed request, and no retry of the trip closes it. **This is the opposite failure to flatten's**, whose account-wide `cancel_all_orders` names no pair and does reach such an order; conflating the two produces the wrong operator instruction and the wrong repair. **The repair owes a venue-side open-order read at trip time, independent of the Cache** — not a wider Cache query, which reads the same populated set — and it must not be modelled on flatten's cache priming: reading 3 above, a distinct-id twin is parsed and then dropped by the execution manager, so "do what flatten does" ships an inert fix.

- **The startup adopt pass is blind to the same order, and that is a SECOND capability gap rather than a restatement of the first.** `executor._adopt_resting_orders` classifies whatever that same `orders_open` list returns, so on the five legs a previous process's resting order is not adopted, not cancelled, and its preserved ledger row is not re-attached; `_reconcile_adopted_rows` looks that row's order up with `cache.order(...)`, gets `None`, and the `continue` that follows logs nothing — so the row is neither reconciled against the venue's figure nor given its terminal state. A later fill on that order then reaches `_on_external_event` with no `_attached` entry to match: counted `unmatched`, logged, and acted on nowhere — no row write, no execution counters, and **no overfill trip**, which is the one kill latch that fill would otherwise arm at boot. The operator consequence is that **a restart is not a way to clear such an order**, which the probe window's restart step and the order-path drills now say. **The trip's repair does not cover this one**: a venue-side read at trip time comes too late for a pass that runs at startup and must classify before it cancels, so a repair taking only the trip leaves the restart path where it is.

**Ripe when either holds, for both consumers together:** the `nautilus-trader` pin in `pyproject.toml` has moved off `2.0.0rc4.dev20260825` — the mechanism was measured on that wheel and nothing on `develop` re-checks it, so a bump owes the reading below before the gap can be called closed or still open; OR an attended engine start on the live account is planned with an order resting at the venue that the starting process did not place. The earlier form of the first arm — "the pinned `nautilus_trader` answers an order-report instrument-cache miss with a diagnostic rather than a dropped row" — was replaced because nothing on `develop` evaluates it: the only procedure that does is the two-loopback-venue A/B, which lives on the parked branch and needs a running `LiveNode`, so it was a condition a reviewer could not read true or false at the index.

**What to run when ripe.** Start the engine against the live account with reconciliation live and at least one order already resting at the venue that the starting process did not place, then look for that order's `client_order_id` in `cache.orders_open(venue=_VENUE)`. A start with no such order cannot separate the two outcomes and proves nothing. **Rest it on a two-way-spelled pair** — BTC/EUR, ETH/EUR, XRP/EUR, LTC/EUR or ETH/BTC — never on SOL/EUR or another coinciding leg: a coinciding pair resolves either way, so a present order there would read as health while the two-way legs stayed invisible, which is the degenerate control this reading exists to avoid. **Safe result:** the order is present, the adopt pass logs a line naming it, and a trip cancels it. **Hazard result:** it is absent, the pass logs nothing about it, and the repair belongs on this repo's side rather than in an upstream report. The reading describes the build it is taken on and nothing else — it must be re-taken against the bumped package once the pin moves.
