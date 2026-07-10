# The shadow node — store, cycle, node, CLI (design)

**Iteration:** iter-083 (attended — the second shadow-engine build iteration; decisions log `[iter-083]`). **Goal:** everything between iter-082's committed builder and a **running local shadow**: the live price store with its seeder (inside the ≈ Jul 25 REST window), the cycle core, the Nautilus node wrapper, and the `zcrypto engine` CLI — closing with an attended first live cycle and a workstation **soak** (dev evidence; the pre-registered gate clock starts only on the VPS in iter-084).

## Directories (human directive, `[iter-083]` item 4)

The legacy empty `runs/` placeholder is **purged**. Both engine data roots live under `data/` — `store_dir = data/engine-store`, `journal_dir = data/engine-journal` (defaults, configurable) — automatically gitignored by `data/.gitignore`'s `*` rule: transactional data is never git-controlled. `data/ohlc-full` remains the frozen regression oracle, never written by the engine (iter-082 constraint). CLAUDE.md's repo-layout line is updated to match.

## The live price store — `cli/engine/store.py`

Canonical layout inside `store_dir`: `<ASSET>/EUR/{1440,240}.parquet`, same schema as the research dataset (`cli.ohlc.dataset` read/write).

1. **Seeder** (`seed_store`): copy the frozen canonical (through 2026-03-31) into the store, then **REST-gap-fill** each pair × grid via `fetch_ohlc` (Kraken returns the trailing 720 bars — the 4h window still reaches 2026-04-01 until ≈ Jul 25). Seam QA: on the overlap between canonical tail and REST rows, closes must match exactly (the holdout pull's precedent — its 621-bar overlap verified exact); a seam mismatch aborts with `EngineError`, never silently prefers a side. Idempotent: re-seeding an existing store only appends missing completed bars (and re-verifies the tail overlap).
2. **Appender** (`refresh_store`, each cycle): fetch both grids per pair; **drop in-progress candles by rule** — any row whose interval end (`stamp + interval`) lies after `now` is dropped (Kraken's OHLC always includes the currently-forming candle as its last row); verify the overlap with the store tail (equal closes on shared stamps, else `EngineError`); append only new completed bars. Venue gaps stay absent (union-calendar semantics downstream); freshness is *enforced later* by the journal boundary invariant, not papered over here.
3. **Pair-key map**: display symbol → Kraken pair key (e.g. `BTC → XXBTZEUR`), one committed constant in `cli/engine/store.py` reusing the exact mapping the canonical dataset / holdout pull used (`cli/universe` / snapshot register source) — the store must produce series continuous with the canonical files it seeds from.

## The cycle core — `cli/engine/cycle.py`

`run_cycle(cycle_ts, *, config, fetch_fn=fetch_ohlc, clock=…) -> CycleResult` — a pure, dependency-injected function (fully testable without network, node, or dataset):

1. **Refresh** the store via the appender; transient fetch errors retry (bounded backoff) while `clock.now() ≤ cycle_ts + 30 min`; the deadline breach itself is journaled, not hidden.
2. **Snapshot**: read full-history `(ts, close)` per pair × grid from the store; **enforce the boundary invariant before building** (per pair: last 4h stamp == `cycle_ts − 4h`; last daily stamp == (last midnight ≤ `cycle_ts`) − 1d). A stale pair ⇒ write a **failed-cycle** record (`validation_failed`, the offending pairs named) and skip the build — per the ratified gate, freshness failure = missed cycle, honestly recorded.
3. **Journal snapshots**: write per-pair×grid snapshot parquet files under the cycle's journal dir; manifest entries with content hashes via **the one shared helper** (`cli.engine.journal.snapshot_content_hash`) — writer and reader never diverge.
4. **Build**: `build_crossfreq_system_fast` (default config) → newest-row `final_targets`.
5. **Intended orders**: `Δtarget = target − previous cycle's journaled target` (first cycle: previous = 0 — the shadow book starts flat, disclosed in the orders log header) × `shadow_nav_eur` ÷ the pair's last close ⇒ per-asset side/quantity/notional appended to a human-readable `orders.jsonl` in the day's journal dir.
6. **Record**: the schema-v1 `CycleRecord` (snapshots manifest, targets, `started_at`/`completed_at`, code version, `builder_path="fast"`) via `to_json`, validated with `validate_record` before write. Layout: `journal_dir/<YYYY-MM-DD>/cycle-<HH>.json` + `snapshots/cycle-<HH>/…`.

## The node wrapper — `cli/engine/node.py`

The production-shape Nautilus `TradingNode` (the iter-079-verified adapter configuration): Kraken data client; **exec client behind `exec_enabled` (default `false`)** — the trade key is IP-bound to the VPS, so local runs are keyless; deployment (iter-084) flips it on for reconciliation-from-day-one. A thin strategy owns only **timer arithmetic**: on start, `set_time_alert` for the next 4h boundary + `settle_delay_secs` (default 90 s — lets Kraken's candle close settle); each alert invokes the cycle core (with retries delegated to it) and schedules the next boundary. **No catch-up**: boundaries missed while the node was down are missed cycles — the journal's absence records them; the gate counts them honestly.

## The CLI — `cli/engine/command.py` (the first Typer sub-app; `app.add_typer` in `cli/__main__.py`)

- `zcrypto engine seed` — build/refresh the store from canonical + REST (idempotent; prints the seam-QA summary).
- `zcrypto engine run` — the node, foreground (the soak runs this under a systemd user service).
- `zcrypto engine cycle [--at ISO_TS]` — one cycle manually (defaults to the most recent elapsed boundary); ops/debugging.
- `zcrypto engine replay [--date YYYY-MM-DD] [--path fast|verified]` — `replay_cycle` + `compare_targets` over journaled cycles (default: all; `--path verified` for the daily spot replay).
- `zcrypto engine report` — `evaluate_gate` over the journal → streak status, last-failure detail.

Loggers `get_logger("engine.<module>")`; README `## Usage` documents the group in the same change (repo rule).

## Config — `[zcrypto.engine]` in `zcrypto.toml`, parsed by `cli/config.py`'s pattern

`store_dir = "data/engine-store"`, `journal_dir = "data/engine-journal"`, `shadow_nav_eur = 1000` (`[iter-083]` item 2), `exec_enabled = false`, `settle_delay_secs = 90`. All optional with these defaults; validation per the existing `FetchConfig` idiom.

## The soak (closeout, attended)

1. `zcrypto engine seed` — the store lands inside the REST window; seam QA printed.
2. One manual `zcrypto engine cycle` at the next boundary, watched live; its `replay` and `report` run immediately after — the first end-to-end evidence.
3. A systemd **user** service (`infra/systemd/zcrypto-engine-shadow.service`, committed as a template + a README note) starts `zcrypto engine run` on the workstation. **Dev evidence only** — labeled as such in the history entry; also keeps the store warm as the rsync fallback for iter-084 if the REST window closes.

## Testing (TDD; no dataset, no network, no live node in CI)

- **Store**: stub `fetch_fn` fixtures — seam-QA pass/mismatch-abort, in-progress-candle drop rule (row whose interval end > now), idempotent re-seed, appender overlap verification, gap tolerance.
- **Cycle**: stub store + fetcher + monkeypatched builder — happy path (record written, hashes verify round-trip via the reader), stale-pair ⇒ failed-cycle record + no build, retry-then-succeed, deadline breach journaled, first-cycle flat-book orders, order arithmetic (Δ × NAV ÷ price).
- **Node**: timer arithmetic unit-tested pure (next-boundary math, settle delay, no-catch-up); the strategy callback wiring with mocks — no live `TradingNode` in tests (the attended soak smoke covers it).
- **CLI**: `CliRunner` over every subcommand with tmp dirs + stubs.
- The one **live smoke** is the attended soak start (step 2 above) — its outputs quoted in the closeout history entry.

## Out of scope

VPS deployment (ansible `engine` role, compose, the §8-hardening gate before the key — iter-084, T0018 constraint 2); order submission and the order state machine (6b); ops drills; any change to the builder, journal schema, or gate semantics (iter-082's contracts are consumed, not revised).
