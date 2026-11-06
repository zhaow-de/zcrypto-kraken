# The engine pages a position the library's reconciliation booked

Branch `feat/00157-reconciliation-position-page`, cut from `develop` aff0b6d30, the merge of #827, on 2026-11-06; the measure below ran on its first parent, d719d15e8. The owner's word that day, verbatim: "i'm sure we will move past dev20261103. is there more prominent way to ensure we won't end up with that trap?", then "yes, build it, and page-only as recommended". The block on a bump past `dev20261103` is #827 and the two-start case is the bump branch's; this spec is the third part, the check on the state itself.

## The measured basis

- **The trap, the `nautilus` session's trace of 2026-11-06** (five throwaway probes on the mock client at upstream df64cfe7b6, the Kraken adapter's lines read only). On a nightly carrying dd8afce410 a reconciliation fill older than `ts_opened` of an open position that lacks its trade id, whose opening order carries the RECONCILIATION tag, goes to the order alone, across strategies on a NETTING account, with no log line. A first start that misses a close a position report already reflects books the gap as an `EXTERNAL` RECONCILIATION order; a second start then sends the older fill order-only. `dev20261103` predates it. The probes are not archived and no installed wheel carries the commit, so nothing a reader of this pair can run proves this paragraph or D1's `VENUE` clause; the first proof a reader can run is the bump branch's `test_a_close_the_first_start_missed_across_two_starts`, on a wheel carrying the commit.
- **The check that exists cannot see it.** `ProbeExecutor._cache_net` (`cli/engine/executor.py`) sums `positions_open(instrument_id=...)` with no strategy filter and `_settle_from_book` compares that with the venue, so own +0.4 and `EXTERNAL` −0.4 read flat beside a flat venue, by reading. `venue_state_from_cache` nets the same way, so sizing sees the true figure.
- **What carries the tag, on the pinned wheel `2.0.0rc9.dev20261101`,** measured 2026-11-06 with `tests/test_cache_restart.py`'s `_Valkey`, `_Node` and `_venue`, a real `valkey-server` and Kraken a scripted loopback, printing each open position's orders from the live Cache in the child. The scratch test and its output are archived under the main checkout's `/home/zhaow/Projects/zcrypto-kraken/.local/reads-archive/feat/00157-reconciliation-position-page/`:

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
- **When the state can change.** The library mints at a start's reconciliation, and `position_check_interval_secs=None` (`cli/engine/node.py`) leaves no periodic pass that mints while running, by the `nautilus` session's reading, which no run here measures: the harness windows are 14 to 20 s and bring no mismatch mid-run. On that reading a tagged position opens no faster than a start; were it wrong, D2's idle read counts the position within a minute while no plan runs, and the WARNING's time says it did not date from a start.
- **What a restart does.** The gauge is process memory, absent until the first read, and re-read at the start's first pass, so a restart re-pages a standing position. The position itself persists in the store until it closes or the store is cleared.
- **Who reads the page.** One operator, attended or by phone, on the main channel through the node's `metrics` receiver.

## D1 — what counts: an open position holding a tagged order

An open position counts when any order in `position.client_order_ids()` reads `RECONCILIATION` in its `tags`, not its opener alone, since the later-mismatch run tags an order on a position whose opener reads `None`. An order `cache.order` cannot return does not count: the store-loss run is the library's own WARN at load, and a lost order is no evidence of a tag. `VENUE` does not count: a hand-settled order carries it or none, and the `nautilus` session's trace shows it cannot trip dd8afce410.

The reader lives in `cli/engine/venuestate.py`, the module that touches Nautilus types, as `reconciliation_booked_positions(cache)`.

## D2 — when it is read: before each book read, and on the idle refresh

`_settle_positions_from_venue` and the boundary's book read each read it first, before the venue call, so a failed book read at a start does not leave a first start's minting unread. `_refresh_gate`, the idle refresh, reads it too, once a minute while no plan runs: with the gate unarmed and no boundary drafting the other two do not recur after the startup pass, so the gauge would not fall when the position closes, and with a boundary drafting it could wait for the next one, up to four hours on. It reads the Cache alone and needs no venue answer.

## D3 — page-only: nothing the engine does changes

The owner's ruling. The read is wrapped as `_publish_fill` and `_settle_from_book` are: a raise logs and continues, and no plan, order, hold or kill reads its result. `net` is right in the trap, by reading, so stopping would turn a bookkeeping error into an outage.

## D4 — the page

- **The gauge.** `zcrypto_exec_reconciliation_positions`, a count, unlabelled, on the engine's exec metrics in `cli/engine/command.py`, registered on its first set as `zcrypto_exec_equity_eur` is, so the series at 0 says a read ran, charted on the engine board.
- **The line.** One WARNING per position per process, naming the position id, its strategy, its signed quantity and the tagged order, so a responder has the facts without a store read. The rule pages, not the line, so the error-log rule does not double it.
- **The rule.** `zcrypto-engine-reconciliation-position`: the gauge above 0.5, `for: 5m`, `noDataState: OK` since the series is absent until the first read after a start, a raising read pages through `zcrypto-engine-error-logs` and a down engine is `zcrypto-engine-cycle-stale`'s, `execErrState: Alerting`, `severity: critical`, receiver `metrics`, in the `zcrypto-gate` group beside `zcrypto-engine-exec-venue-diverged`. `for: 5m` keeps a critical rule out of the `for: 0s` set one failed evaluation fires, and costs no detection, since the count stands until the position goes.
- **It stands until the position goes.** It resolves when the position closes or the store is cleared through `engine-procedures.md#engine-clear-stored-account-prefix-wide`, which is what the runbook's procedure ends in; the single-key form at `#engine-clear-stored-account` leaves the position and the rule firing. Until then the page repeats on the node's `metrics` policy. No page advises a silence: the series is one unlabelled count, so a silence outlives its position and covers what the next start books, the one state this pair pages. An owner may still silence by hand.

## D5 — the runbook

`infra/runbooks/engine.md#zcrypto-engine-reconciliation-position`: what you are seeing; what it means, that the library booked a difference from a venue position report it could not explain under `EXTERNAL`, and, by the `nautilus` session's trace, that a later nightly can hide a close behind it; what to do. Read the WARNING, and Kraken with `kraken positions -o json` and `kraken extended-balance -o json` on the workstation; explain the gap as one of the table's shapes; and, before the next restart on a build past `dev20261103`, clear it at a flat book through `engine-procedures.md#engine-clear-stored-account-prefix-wide`. Flat reads as `kraken open-orders -o json` listing nothing, `kraken positions -o json` printing `{}` and `kraken extended-balance -o json` showing no lot, since the positions read prints `{}` with a spot lot held, and that form's own admit step gains the balance export. Not flat, a lot or a margin position held: no clear. On a build at or before `dev20261103` the position may stand, with no bump past `dev20261103` until it is cleared at a flat book; on a build past it the next restart you schedule goes to the owner first. Flattening to clear is the owner's decision. `zcrypto-bump-nautilus` reads the gauge at 0 by value before the merge of a pin past `dev20261103`, Step 6 item 1, and again immediately before that wheel's rollout, Step 6 item 2, and `zcrypto-rollout-image`'s *Engine converges* takes the same read before a converge that starts such a wheel, since an unrelated engine image carries a merged pin: an owner's read at each, nothing the engine does, and a pin past that limit owes it. That one bar is `_NEWEST_PIN_WITHOUT_THE_TWO_START_CASE` in `tests/test_nautilus_adapter.py`, whether or not a wheel past it carries the commit.

`engine-procedures.md`'s rung-3 restart read and its daily *The Cache against Kraken* item pass the gauge at 0 alone: a non-zero count names the position by its WARNING and the owner decides, and the tile's `NOT READ YET` is a read that has not run or has raised. That section's restart by hand reads the gauge at 0 before a restart on a build past `dev20261103`, and its go/no-go's unreconciled-state list names the gauge. `engine.md#zcrypto-engine-error-logs` step 2 classes the read's raise line as telemetry: no disarm is owed for it alone, and the gauge says nothing while it stands.

## D6 — two proofs

- A case in `tests/test_cache_restart.py` on the real wheel: a leveraged row the Cache does not hold at a cold start counts 1, and, in their own runs since a cold start restores nothing, a restored margin position, a spot lot and a hand order count 0. `zcrypto-bump-nautilus` Step 3 already runs this file, so a wheel that renames the tag or moves the read goes red at the bump.
- Unit cases on the reader and the executor's wrapper, with `tests/test_engine_stub_fidelity.py` classifying any double the reader touches.

## D7 — the rollout

The rule first, by the node push, since `noDataState: OK` leaves it quiet; the image second. #826 merged and every Alloy converged on 2026-11-06, so the fleet ships to the node alone, and the push and the reads are the node's. The image rides the weekend's bulk rollout if this merges before it, else the next engine image; that rollout is the owner's word of 2026-11-06, "defer the bulk rollout, we do it over the weekend", held in the owner's queue, which stays closed to readers. The engine's pin stays `dev20261101` until half a day before rung 3, then `dev20261103`. The gauge reading 0 after the engine's first start on it, by value, is the proof, since only a read sets the series; beside it, the owner's `sudo docker inspect --format '{{.State.Status}} {{.RestartCount}}' zcrypto-engine` on the host is the Operating model's one-process premise read at its container. A `cli/engine/` change moves `replay_fingerprint`, so that image's gate export replays cold, as the weekend's does already.

## Out of scope

- Refusing to trade a leg, on the owner's ruling. Closing or netting the `EXTERNAL` position in the Cache: the store clear is the existing procedure. Comparing the engine's own strategy-scoped position with the venue: a hand settle reads the same shape with no tag, by the hand-order runs, and would page on a sanctioned act. Two explicit drops: shipping the Rust core's stdout to Loki, since the gauge and the WARNING carry the state and that line adds nothing to them; and dust-lot behaviour itself, where the table's run is a scratch plan and whether a live plan leaves one is unmeasured, since a dust lot that mints a tagged position pages and the runbook's list of shapes names it.
