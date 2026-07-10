# Shadow Node Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement spec `docs/specs/00041-shadow-node-design.md`: the live price store + seeder, the cycle core, the Nautilus node wrapper, and the `zcrypto engine` CLI — ending with an attended first live cycle and a workstation soak.

**Architecture:** Four subagent TDD tasks in dependency order — (1) engine config + store, (2) cycle core, (3) node wrapper, (4) CLI + docs — then the orchestrator's attended soak + closeout. The spec is law; iter-082's `cli/engine` journal/concordance and `cli/portfolio` builder contracts are consumed, never modified.

**Tech Stack:** Python 3.14, existing `cli` machinery (`cli.ohlc.fetch/dataset`, `cli.engine.journal/concordance`, `cli.portfolio.crossfreq_system`), nautilus-trader 1.230.0, Typer, pytest with injected fakes.

## Global Constraints

- **Aware-UTC everywhere** (spec §cycle 8): `cycle_ts`, timings, snapshot ts, sidecar fields, `evaluate_gate`'s `now`; the injected `clock` returns aware-UTC (`datetime.now(timezone.utc)` default); mixed awareness is rejected at the cycle boundary with a clear error.
- **No changes** to `cli/engine/journal.py`, `cli/engine/concordance.py`, `cli/portfolio/*` — consumed as-is. `validate_record` applies to **success records only**; failures use the sidecar (spec §cycle 7).
- **`data/ohlc-full` is read-only**; the store/journal live at `data/engine-store` / `data/engine-journal` defaults (gitignored via `data/.gitignore`).
- Seeder guards (spec §store 1): ≥ 6 shared stamps per pair × grid overlap (else the distinct **window-shortfall** error naming the OHLCVT-dump fallback) AND exact close equality on the overlap; re-seed may replace divergent tail rows within the REST window (logged).
- Refresh reserve: retries bounded by `clock() ≤ cycle_ts + 25 min`; the ratified gate deadline (30 min) is never the retry cutoff.
- Ruff 132/double quotes; gate `uv run pre-commit run -a`; actual-model trailers + `Claude-Session`; subagent review + `Reviewed-by` before push.

______________________________________________________________________

### Task 1 (subagent, TDD): engine config + the live price store

**Files:** Modify `cli/config.py` (add `EngineConfig` + `AppConfig.engine`), create `cli/engine/store.py`, extend `tests/` with `tests/test_engine_store.py` (+ config tests in the existing config test file — find it via `grep -rl FetchConfig tests/`).

**Interfaces (produces):**

```python
# cli/config.py
@dataclass(frozen=True)
class EngineConfig:
    store_dir: Path = Path("data/engine-store")
    journal_dir: Path = Path("data/engine-journal")
    shadow_nav_eur: float = 1000.0
    exec_enabled: bool = False
    settle_delay_secs: int = 90
# parsed from [zcrypto.engine]; unknown keys rejected (ConfigError); per-field typed checks
# (str/Path, real bool — isinstance(v, bool) precedes the int check, positive numbers);
# committed zcrypto.toml stays unchanged (defaults in code, the [zcrypto.fetch] precedent).

# cli/engine/store.py
PAIR_KEYS: dict[str, str]  # the 10 EUR pairs, transcribed from docs/research/01.1.kraken-snapshot-register.md
GRID_INTERVALS = (1440, 240)
@dataclass(frozen=True)
class SeedReport:   # per pair x grid: overlap_bars, appended, replaced_tail_rows
@dataclass(frozen=True)
class RefreshReport # per pair x grid: appended, tail_fresh_through
def seed_store(store_dir: Path, canonical_dir: Path, *, fetch_fn=fetch_ohlc, clock=_utc_now) -> SeedReport
def refresh_store(store_dir: Path, *, pairs=PAIR_KEYS, fetch_fn=fetch_ohlc, clock=_utc_now) -> RefreshReport
def read_store_series(store_dir: Path, asset: str, interval: int) -> tuple[list[datetime], list[float | None]]
```

Kraken OHLC rows are `[time, open, high, low, close, vwap, volume, count]` with epoch-second `time` (see `cli/ohlc/ingest.py`'s `to_frame` for the conversion convention — reuse it). The **drop rule**: any row whose `stamp + interval` > `clock()` is dropped. Store files use `cli.ohlc.dataset.write_parquet/read_parquet` (same schema as canonical).

Steps: failing tests first — PAIR_KEYS content vs the snapshot-register table (hardcode the 10 expected mappings in the test); seeder happy path (stub canonical dir with tiny parquet fixtures + stub fetch: overlap verified, gap filled); **window-shortfall** (stub fetch whose oldest row post-dates the canonical tail → distinct error message mentioning "OHLCVT"); overlap mismatch abort; idempotent re-seed (appends only missing); divergent-tail replace-on-reseed (logged in the report); refresh drop-in-progress rule (row with interval end > now dropped; boundary-exact row kept); refresh overlap mismatch → `EngineError`; config parsing (defaults, overrides, unknown key, bool/int/path type rejections). Then implement; file green; full suite; pre-commit; commit `feat(engine): engine config + live price store (seeder, appender, pair keys)`.

### Task 2 (subagent, TDD): the cycle core

**Files:** Create `cli/engine/cycle.py`, `tests/test_engine_cycle.py`; extend `cli/engine/__init__.py` re-exports.

**Interfaces (consumes):** Task 1's store API + `EngineConfig`; `cli.engine.journal` (CycleRecord, SnapshotEntry, snapshot_content_hash, validate_record, to_json); `cli.portfolio.build_crossfreq_system_fast`. **Produces:**

```python
@dataclass(frozen=True)
class CycleResult:
    status: str                      # "success" | "failed"
    cycle_ts: datetime
    record_path: Path | None         # success
    sidecar_path: Path | None        # failed
    targets: dict[str, float] | None
    orders: list[dict] | None        # [{asset, side, quantity, notional_eur, price}]
    reason: str | None               # "stale_pair" | "refresh_deadline"
    offending_pairs: tuple[str, ...] | None
def run_cycle(cycle_ts: datetime, *, config: EngineConfig, fetch_fn=fetch_ohlc, clock=_utc_now) -> CycleResult
```

Implement spec §cycle steps 1–8 exactly: settle-verify refresh loop (per-pair re-fetch when the raw tail lacks `cycle_ts − 4h`, bounded by the 25-min reserve); raw-series staleness check; union-align per grid (`None` at absences — the shape `build_crossfreq_system_fast` and `replay_cycle` both require); snapshot parquets at `<date>/snapshots/cycle-<HH>/<ASSET>-<grid>.parquet` with **relative** `SnapshotEntry.path`; hashes via the shared helper; build with default config; orders (Δ vs the most recent successful record's targets — search back; ÷ the 4h close at `cycle_ts`; append `orders.jsonl`); the validated success record OR the failed-cycle sidecar JSON (`{cycle_ts, attempted_at, completed_at, reason, offending_pairs}`, ISO-8601 aware-UTC). Tests per the spec's list (stub store/fetch/builder — no dataset, no network): happy path with reader round-trip (`replay_cycle` on the written record with a monkeypatched builder returning the same targets → compare passes), stale-pair sidecar + no build, settle-verify recovery, refresh-deadline sidecar, first-cycle flat orders, orders-across-a-gap, order arithmetic, union-alignment + venue-gap replay-clean, journal-relocation round-trip, naive/aware-mix rejection. Commit `feat(engine): the shadow cycle core (run_cycle)`.

### Task 3 (subagent, TDD): the node wrapper

**Files:** Create `cli/engine/node.py`, `tests/test_engine_node.py`; extend `cli/engine/__init__.py`.

**Produces:**

```python
def next_boundary(now: datetime) -> datetime          # next 00/04/08/12/16/20 UTC boundary strictly after now
def most_recent_boundary(now: datetime) -> datetime   # most recent boundary <= now
def startup_action(now, journal_dir) -> datetime | None  # B if no record/sidecar for B and now <= B + 25min, else None
def build_shadow_node(config: EngineConfig) -> TradingNode  # iter-079 adapter config; exec client only when exec_enabled
class ShadowStrategy(Strategy)  # timers: alert at boundary + settle_delay_secs; schedules NEXT alert BEFORE invoking run_cycle
```

Timer math is pure and exhaustively unit-tested (boundary arithmetic at edges: exactly-on-boundary now, 20:00→00:00 day rollover; startup_action's three branches). The strategy is tested with mocks (clock alerts fire → next alert scheduled first → run_cycle invoked with the right cycle_ts; run_cycle exceptions logged, never propagate to kill the node). `build_shadow_node` mirrors the iter-079 probe configuration (`KrakenDataClientConfig`/`KrakenExecClientConfig(spot_account_type=MARGIN, margin_balance_asset="ZEUR")` behind `exec_enabled`, `LoggingConfig`, factories registered); it is assembled but NOT run in tests (the attended soak is the live smoke). Commit `feat(engine): shadow node wrapper (timers, startup arithmetic, TradingNode assembly)`.

### Task 4 (subagent, TDD): the CLI + docs

**Files:** Create `cli/engine/command.py`, `tests/test_engine_command.py`; modify `cli/__main__.py` (`app.add_typer(engine_app, name="engine")`), `README.md` (Usage: the `zcrypto engine` group + a `### [zcrypto.engine]` table under `## Configuration`), `CLAUDE.md` (drop `cli/engine` from the no-command examples parenthetical), create `infra/systemd/zcrypto-engine-shadow.service` (user-unit template: `Restart=on-failure`, `WantedBy=default.target`; header comment documenting `loginctl enable-linger` + install steps).

Subcommands per spec §CLI: `seed` (prints the per-pair overlap summary), `run` (build_shadow_node + node.run()), `cycle [--at ISO_TS] [--replace]` (grid-enforced, refuse-existing by default), `replay [--date] [--path fast|verified]` (classifies `EngineJournalError`→validation-failed, `HashMismatchError`→mismatch, sidecars→failed; never crashes the sweep), `report` (replay-on-demand path=fast → `CycleOutcome`s → `evaluate_gate(now=aware-UTC)` → streak + last-failure). Loggers `get_logger("engine.command")`. Tests: `CliRunner` on every subcommand with tmp dirs, stub fetch/builder via monkeypatch, `--at` off-grid rejection, `--replace` semantics, report classification mapping. Commit `feat(cli): zcrypto engine subcommand group + shadow service template`.

### Task 5 (orchestrator, attended): soak + closeout

- [ ] `uv run zcrypto engine seed` — real REST, inside the window; verify the printed per-pair overlap counts (expect ≥ 6 everywhere) and seam QA.
- [ ] At the next 4h boundary: `uv run zcrypto engine cycle` watched live; then `engine replay` (fast + verified) and `engine report` — first end-to-end evidence, quoted in the history entry.
- [ ] Install the systemd user service (`loginctl enable-linger` first, verify `-p Linger`); confirm the unit is active and waiting.
- [ ] T0018 closeout sync: constraint 3 gains the **rsync-from-workstation fallback** (store seeded/warm) + journal disk sizing (~0.3 GB/month) as an iter-084 input; Done-so-far gains iter-083.
- [ ] Iterations-history entry (incl. the soak's first-cycle outputs and the dev-evidence label); pre-commit; commit; PR into develop titled `feat(engine): iter-083 — the shadow node (store, cycle, node, CLI) + workstation soak`; merge held for the human's go.
