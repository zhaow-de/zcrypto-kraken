# The engine pages a position the library's reconciliation booked

Branch `feat/00157-reconciliation-position-page`, cut from `develop` d719d15e8 on 2026-11-06. The owner's word that day, verbatim: "i'm sure we will move past dev20261103. is there more prominent way to ensure we won't end up with that trap?", then "yes, build it, and page-only as recommended". The block on a bump past `dev20261103` is #827 and the two-start case is the bump branch's; this spec is the third part, the check on the state itself.

## The measured basis

- **The trap, the `nautilus` session's trace of 2026-11-06** (five throwaway probes on the mock client at upstream df64cfe7b6, the Kraken adapter's lines read only). On a nightly carrying dd8afce410 a reconciliation fill older than `ts_opened` of an open position that lacks its trade id, whose opening order carries the RECONCILIATION tag, goes to the order alone, across strategies on a NETTING account, with no log line. A first start that misses a close a position report already reflects books the gap as an `EXTERNAL` RECONCILIATION order; a second start then sends the older fill order-only. `dev20261103` predates it.
- **The check that exists cannot see it.** `ProbeExecutor._cache_net` (`cli/engine/executor.py`) sums `positions_open(instrument_id=...)` with no strategy filter and `_settle_from_book` compares that with the venue, so own +0.4 and `EXTERNAL` −0.4 read flat beside a flat venue, by reading. `venue_state_from_cache` nets the same way, so sizing sees the true figure.
- **What carries the tag, on the pinned wheel `2.0.0rc9.dev20261101`,** measured 2026-11-06 with `tests/test_cache_restart.py`'s `_Valkey`, `_Node` and `_venue`, a real `valkey-server` and Kraken a scripted loopback, printing each open position's orders from the live Cache in the child. The scratch test and its output are archived under `.local/reads-archive/feat/00157-reconciliation-position-page/`:

| Run | `Reconciliation complete` | Open positions, strategy, quantity, opener's tags |
|---|---|---|
| A margin position restored | `reconciled=1`, then all 0 | `ShadowStrategy-000` 0.4 `None` |
| A spot lot restored | all 0 | `ShadowStrategy-000` 1 `None` |
| A fill made while down, in TradesHistory | `reconciled=1, fills=1` | `ShadowStrategy-000` 0.7 `None` |
| A hand order's fill, seen live | all 0 | `EXTERNAL` 0.5 `None` |
| A hand order in the history, cold start | `external=1, fills=1` | none |
| A leveraged row the Cache does not hold, cold start | `positions=1` | `EXTERNAL` 0.5 `['RECONCILIATION']` |
| The same, restarted | all 0 | `EXTERNAL` 0.5 `['RECONCILIATION']` |
| A leveraged row differing from the Cache's net | `positions=1` | `EXTERNAL` −0.5 `['RECONCILIATION']`, `ShadowStrategy-000` 1 `None` |
| A fill made while down, absent from TradesHistory | `positions=1` | `EXTERNAL` 0.3 `['RECONCILIATION']`, `ShadowStrategy-000` 0.4 `None` |
| A store lost, the fill past the 720-minute lookback | `positions=1` | `EXTERNAL` 0.4 `['RECONCILIATION']` |
| The engine's dust lot beside its own margin fill | `positions=1` | `EXTERNAL` −0.005 `['RECONCILIATION']`, `ShadowStrategy-000` 1.005 `None` |
| A later mismatch on a hand-opened position | `positions=1` | `EXTERNAL` 0.8 opener `None`, a tagged order in `client_order_ids()` |
| The tagged order's key deleted from the store | all 0 | `EXTERNAL` 0.5, `cache.order(...)` returns `None` |

- **How it reads from Python on this wheel.** `order.tags` is `list[str] | None`; the strings are `RECONCILIATION` and `VENUE`. `position.client_order_ids()` is a method. `cache.order(id)` returns `None` without raising for an id it does not hold. The tag survives a restart. No run minted an order under the engine's own strategy id.
- **What the engine's plain running shows.** Three starts on `zcrypto` since 2026-11-03, none logging a restored position (`grafana-query.py --loki` over `cache restore: position`, no series), the engine flat.
- **The log line is not a way in.** `Reconciliation complete … positions=N` marks each minting run above, but it is the Rust core's stdout: `{host="zcrypto", container="engine"} |= "Reconciliation complete"` over five days reads no series on the node.

## Operating model

- **Machines and processes.** One engine process, the `zcrypto-engine` service, on `zcrypto`. It alone reads this Cache and publishes the gauge.
- **When the state can change.** The library mints at a start's reconciliation, and `position_check_interval_secs=None` (`cli/engine/node.py`) leaves no periodic pass that mints while running, by the `nautilus` session's reading. A tagged position opens no faster than a start.
- **What a restart does.** The gauge is process memory, absent until the first read, and re-read at the start's first pass, so a restart re-pages a standing position. The position itself persists in the store until it closes or the store is cleared.
- **Who reads the page.** One operator, attended or by phone, on the main channel through the node's `metrics` receiver.

## D1 — what counts: an open position holding a tagged order

An open position counts when any order in `position.client_order_ids()` reads `RECONCILIATION` in its `tags`, not its opener alone, since the later-mismatch run tags an order on a position whose opener reads `None`. An order `cache.order` cannot return does not count: the store-loss run is the library's own WARN at load, and a lost order is no evidence of a tag. `VENUE` does not count: a hand-settled order carries it or none, and the peer's trace shows it cannot trip dd8afce410.

The reader lives in `cli/engine/venuestate.py`, the module that touches Nautilus types, as `reconciliation_booked_positions(cache)`.

## D2 — when it is read: before each book read

`_settle_positions_from_venue` and the boundary's book read each read it first, before the venue call, so a failed book read at a start does not leave a first start's minting unread. It reads the Cache alone and needs no venue answer.

## D3 — page-only: nothing the engine does changes

The owner's ruling. The read is wrapped as `_publish_fill` and `_settle_from_book` are: a raise logs and continues, and no plan, order, hold or kill reads its result. `net` is right in the trap, by reading, so stopping would turn a bookkeeping error into an outage.

## D4 — the page

- **The gauge.** `zcrypto_exec_reconciliation_positions`, a count, unlabelled, on the engine's exec metrics in `cli/engine/command.py`, charted on the engine board.
- **The line.** One WARNING per position per process, naming the position id, its strategy, its signed quantity and the tagged order, so a responder has the facts without a store read. The rule pages, not the line, so the error-log rule does not double it.
- **The rule.** `zcrypto-engine-reconciliation-position`: the gauge above 0.5, `for: 0s`, `noDataState: OK` since the series is absent until the image rolls and its absence after that is `zcrypto-engine-cycle-stale`'s, `severity: critical`, receiver `metrics`, in the `zcrypto-gate` group beside `zcrypto-engine-exec-venue-diverged`.
- **It stands until the position goes.** It resolves when the position closes or the store is cleared, which is what the runbook's procedure ends in. A standing firing rule repeats on the node's policy; the responder silences it by its uid for a state they have explained, with a dated end.

## D5 — the runbook

`infra/runbooks/engine.md#zcrypto-engine-reconciliation-position`: what you are seeing; what it means, that the library booked a difference from a venue position report it could not explain under `EXTERNAL`, and that a later nightly can hide a close behind it; what to do. Read the WARNING and Kraken's positions with `kraken` on the workstation; explain the gap as one of the table's shapes; and, before the next restart on a build carrying dd8afce410, clear it: at a flat book through `engine-procedures.md`'s store clear. `engine-procedures.md`'s rung-3 restart read and its unreconciled-state list name the gauge.

## D6 — two proofs

- A case in `tests/test_cache_restart.py` on the real wheel: a leveraged row the Cache does not hold at a cold start counts 1, and the same start's restored margin position, spot lot and hand order count 0. `zcrypto-bump-nautilus` Step 3 already runs this file, so a wheel that renames the tag or moves the read goes red at the bump.
- Unit cases on the reader and the executor's wrapper, with `tests/test_engine_stub_fidelity.py` classifying any double the reader touches.

## D7 — the rollout

The rule first, by the node push, since `noDataState: OK` leaves it quiet; the image second. The image rides the weekend's bulk rollout if this merges before it, else the next engine image. The gauge reading 0 after the engine's first start on it, by value, is the proof. A `cli/engine/` change moves `replay_fingerprint`, so that image's gate export replays cold, as the weekend's does already.

## Out of scope

- Refusing to trade a leg, on the owner's ruling. Closing or netting the `EXTERNAL` position in the Cache: the store clear is the existing procedure. Comparing the engine's own strategy-scoped position with the venue: a hand settle reads the same shape with no tag, by the hand-order runs, and would page on a sanctioned act. Shipping the Rust core's stdout to Loki. Dust-lot behaviour itself, where the table's run is a scratch plan and whether a live plan leaves one is unmeasured.
