# The journal's snapshot write refuses an unusable close before the first file is written

## Problem

`run_cycle` journals every cycle's inputs as one snapshot per pair and grid through `_journal_snapshots` in `cli/engine/cycle.py`, and nothing at that write reads the closes it hashes ([[T0200]]): a store close that is NaN, infinite, zero or negative at a stamp outside the refresh overlap is written into the snapshot and packed into its `content_hash` as though it were a price. What happens next depends on which leg holds it, measured below: on one of the ten EUR legs the builder's own validator refuses the cycle afterwards, so the boundary ends journal-absent with a full set of snapshot files under it that no record names; on one of the two BTC-quoted legs, which no builder input reads, the cycle succeeds, publishes a target and leaves the value in a journaled record that every later reader either refuses ([[T0193]]'s `_validate_grid`, the reports path) or filters (the soak's usable-close filter). The record's writer is the one actor that still holds the frame and has not yet published, and today the read pays for what the write let through.

The owner ruled on 2026-09-20, in chat, on the analysis the memo entry records: the refusal lives at the engine's own write, inside `_journal_snapshots` before `write_parquet`; no new `SnapshotEntry` field; the shared `write_parquet` stays untouched; on a refusal the cycle aborts without publishing a target, naming grid, asset, bar and value; `None` at a union absence is admitted. This spec records that ruling as D1 to D5 and settles the two things it left open, the abort's journal shape (D6) and its operator reading (D7).

## Decisions

**D1. The refusal is the engine's own, at `_journal_snapshots`, over every close of every grid before the first file is written.** The function walks the union-aligned closes it is about to hash, the same lists `snapshot_content_hash` packs, and refuses a present close that is not a finite positive number, raising `EngineError` naming the pair, the grid, the bar index, the bar's stamp and the value. The walk finishes over all twenty-four series before any `write_parquet` call, so a refused boundary leaves no `snapshots/cycle-<HH>/` directory at all, where today's EUR-leg case leaves twenty-four files nothing references and the next reader has to know are orphans. The predicate is the value half of `_validate_grid`'s, `None` or finite and positive: a value the read would refuse tomorrow is one the write refuses today. The type half is already `read_store_series`'s, which admits nothing but `int`, `float` and `None` into these lists. The cost is one Python pass over the cycle's closes, 25 ms measured over a cycle's share.

**D2. `None` at a union absence is admitted; the claim is about present closes only.** `_union_align` writes `None` where a leg lacks a stamp another leg carries, `snapshot_content_hash` packs it as NaN by design, and the replay and the builder both read `None` as absence. The refusal reads `close is not None` first and asks nothing else of a `None`.

**D3. No new `SnapshotEntry` field and no schema bump: the claim is enforced, not declared.** A field would say "the writer checked" and cost a `schema_version` step, a reader migration and a second place the claim could drift from its check. A refusal at the write makes the claim true of every record written from this commit on, and a record's `code_version` at or past it is the claim. Records written before it carry no claim and are what D5 keeps the read's refusal for.

**D4. The shared `write_parquet` in `cli/ohlc/dataset.py` stays untouched, and this records for [[T0199]] that its helper arm is not the door.** The helper serves the OHLC, backfill and derivatives packages, and two of its callers write frames with no close column, so a close-value door there could not be unconditional, [[T0199]]'s own finding; the engine's write is the one site that knows it is writing closes. T0199's other halves, the seam's null close, the store door's width, the dropped-tail reason and the store recovery text, are its own, and this spec moves none of them.

**D5. The read-side refusal stays.** [[T0193]]'s `_validate_grid` refuses a non-finite close in a record it replays and the degrade net reports it, and the soak's usable-close filter stays too. They are what reads a record written before this commit, and the write door does not replace them: a write-side check is a claim about future records, a read-side one about the record in hand.

**D6. The abort's shape is the raise, not a sidecar.** `run_cycle` lets the `EngineError` propagate exactly as a store data-integrity failure from `refresh_store` does and as the forming-row guard does: `_invoke_cycle` in `cli/engine/node.py` logs `shadow node: run_cycle(<ts>) raised; the boundary stays journal-absent` with the traceback carrying the refusal's message; no `cycle-<HH>.json`, no `failed-cycle-<HH>.json`, no `orders.jsonl`, no healthchecks.io ping. `startup_action` re-runs the boundary only inside the 25-minute reserve, and a re-run over the same store refuses the same way, so the boundary is lost until the store is repaired, and `zcrypto-engine-cycle-stale` pages it. The failed-cycle sidecar is not taken: it is the shape of a cycle the engine could not complete for a reason the next boundary may not repeat, a refresh past its deadline or a stale pair, and it refreshes the completion gauge; an unusable close in the store repeats at every boundary until someone repairs the store, which is the class `run_cycle`'s docstring already routes to the raise and to `zcrypto engine seed`, and a third sidecar reason would widen a record shape the gate and the daily pass read.

**D7. The operator reading is the runbook's existing bullet, extended by the message.** `infra/runbooks/engine.md`, under `zcrypto-engine-cycle-stale` › What it means, already lists "`run_cycle` raised before writing anything: a poisoned store, a disk error"; it gains the sentence that a message naming a pair, a grid, a bar and a close that is not a finite positive number is the store holding that value at that stamp, and that the recovery is the store's, not the cycle's. No new alert, metric or log line: the raise reaches the operator through the two rules that already read a missing boundary, `zcrypto-engine-cycle-stale` and the healthchecks.io silence, and the message reaches them through the traceback the node already logs.

## The measured basis

- **No journaled snapshot on disk holds an unusable present close.** Over the NAS journal mirror on 2026-09-21: 433 success records, 9,508 snapshot files, 156,359,450 close rows, 62,997,555 of them `None` (union absences) and 0 present closes that are non-finite or non-positive. The door is preventive; nothing on disk is refused by it. The command:

```
uv run python - <<'EOF'
import math, polars as pl
from pathlib import Path
root = Path("/mnt/zhao-crypto/engine-journal")
paths = sorted(root.glob("*/snapshots/cycle-*/*.parquet")); records = sorted(root.glob("*/cycle-*.json"))
bad = []; rows = 0; nulls = 0
for p in paths:
    c = pl.read_parquet(p)["close"]; rows += len(c); nulls += c.null_count()
    bad += [(p.name, k, v) for k, v in enumerate(c.to_list()) if v is not None and (not math.isfinite(v) or v <= 0)]
print(f"records={len(records)} snapshot_files={len(paths)} close_rows={rows} null_closes={nulls} unusable_present_closes={len(bad)}")
EOF
```

- **What a NaN close in the store does to a cycle today**, driven through `tests/test_engine_cycle.py`'s fixtures with the real builder over 420 4h bars, the NaN written below `to_frame` (which refuses it) by polars directly: on `ETH/EUR@240` at bar 210, twenty-four snapshot files are written and then `build_crossfreq_system_fast` raises `PortfolioError: h4_prices['ETH'][210] must be None or a finite positive number, got nan`, no record, no orders, the files orphaned; on `ETH/BTC@240` at bar 210 the cycle succeeds, record, orders and the NaN packed into `ETH-BTC-240.parquet`; a NaN inside the refresh overlap, the last two bars, is refused before anything is written, by `refresh_store`'s overlap mismatch, because NaN compares unequal to itself. With the stubbed builder both mid-series cases succeed, which is why the plan's cases use the stub: the write door is then the only refusal in the path, on either leg.
- **The pre-pass costs 25 ms per cycle**: a Python loop over 361,107 closes, one cycle's share of the rows above, with the D1 predicate, measured on the workstation.
- **Where the class already refuses**: `_validate_grid` in `cli/portfolio/crossfreq_system.py` (a present close must be `None` or a finite positive number, at the builder and at the replay), the forming-row guard in `run_cycle` (`None` or unusable at the forming row, before the orders), and `refresh_store`'s overlap mismatch (a NaN on a shared stamp). D1's predicate is the first one's, so the two doors agree on every value.

## Out of scope

- [[T0199]]'s arms, the seam's null close, the store door's width, `dropped_tail`'s reason and the store recovery text: the topic's own, ruled separately; D4 records only what this spec decided about their shared helper.
- `read_store_series` refusing a non-finite close at the store read: spec 00059 D7 rules only the rebuild-unavailable case, no decision rules on a store NaN, and the store read stays as it is; the journal write refuses.
- The two BTC-quoted legs entering the builder's inputs: the write door closes the journal to their unusable closes; what the model reads is spec 00094's.
