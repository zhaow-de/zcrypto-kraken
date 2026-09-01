---
status: open
ripe_when: 'fired — that PR merged 2026-09-01 (904862a8), so this is live work; it runs only once the engine is converged onto 00106 + rest-hold and the flatten baseline press has been taken on the current pin, and never shares a window with either'
---

# T0160 — nautilus-trader nightly bump, and the flatten contract checks it must not skip

## Context — what

The repo pins `nautilus-trader===2.0.0rc4.dev20260825` (`pyproject.toml`, index `nautechsystems`). On 2026-08-31 a scan of `nautechsystems/nautilus_trader` counted **154 commits merged since that nightly**. Three of them touch surfaces `cli/engine/flatten.py` depends on, and one of those is a latent behaviour change that would make the flatten command refuse to run rather than fail loudly.

The bump itself is trivial. This topic exists because the **checks that must ride with it** are not, and they are not derivable from the diff — they come from knowing which upstream changes intersect this repo's read path.

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

## Suggested next steps

Do these **on the bump branch, before merging it** — each one names what to run and what result means "safe".

- **Bump and lock.** Edit the pin in `pyproject.toml` to the chosen nightly, `uv lock`, `uv sync`. Per `CLAUDE.md` a `uv.lock` / `pyproject.toml` change reaches everything, so this branch takes the **full local suite**, not a reachable subset.
- **Check the side-enum change against `position_side`, first and before anything else.** Run a real `request_position_status_reports` against the account (reads only) with at least one open margin position and at least one flat/closed row, and print `repr(row.position_side)` for every row. **Safe result:** flat rows still carry a `FLAT`-like sentinel that `str()`s to `"FLAT"`. **Hazard result:** any row reports `position_side is None` — then `_required(row, "position_side", …)` raises `FlattenUnreachable` and `run_flatten` exits 3, i.e. the command **refuses to flatten an account** instead of skipping that row. If the hazard result appears, fix `cli/engine/flatten.py`'s flat-row handling in the same PR; do not merge the bump alone.
- **Re-measure the async surface** exactly as recorded under *Findings so far*: call `request_instruments()` outside a loop (expect a raise) and inside one (expect an awaitable). If `Standardize adapter task lifecycles` changed either, `cli/engine/flatten.py`'s `Recorder.call` and the `asyncio.run` boundary in `cli/engine/command.py` need revisiting together.
- **Re-measure `OrderBook.bids` / `.asks` kind.** `getattr(OrderBook, "bids")` must still be callable; `read_book_price` calls `book.bids()`. If they became properties, that call inverts.
- **Re-run the flatten contract pin** added with the async correction (the env-gated one) and say in the PR what it proved and what it did not.
- **Read the Kraken correlation fix's own tests** to learn what "unknown outcome" the adapter now reports, and check whether `cli/engine/flatten.py`'s `post_write_failure` / exit-2 path should record it distinctly rather than as a generic transport failure.
- **Scan the remaining ~150 commit headers for adapter- and model-level changes** not covered above (`gh api "repos/nautechsystems/nautilus_trader/commits?since=<pinned nightly date>T00:00:00Z&per_page=100" --paginate --jq '.[] | .commit.message | split("\n")[0]'`), and record any new intersection in this file before closing it.
