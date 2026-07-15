# L2 primitive panel (OPS-4) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Materialize the captured depth-100 L2 book into the 1-second wide primitive panel (spec `00052`): `cli/panel/` + `zcrypto panel materialize`, hourly ops-node timers (recurring NAS pull + materialize), NAS replication, and the ~3,400-hour backfill — ending at *panel exists, verified, replicating, accruing hourly*.

**Architecture:** batch-per-hour materialization over the canonical (reconciled-first) archive: `canonical_segments` → `regroup_messages` → `OrderBook` walk → 1 Hz state samples → wide primitive rows → atomic hourly parquet + `.sha256`. Watermarked hourly increments; generation-versioned via `panel-meta.json`.

**Tech Stack:** polars, the existing `OrderBook`/replay machinery, systemd timers in the digest-pinned AVX container, rrsync channels.

## Global Constraints

- Spec `00052` D1–D9 govern; the decisions are logged `[iter-098]` (phase-1 running log) — grid and primitive set are **not** re-litigated here.
- Panel rows are emitted **only from the hour's snapshot onward** (no pre-snapshot samples); `fill_bps_*` is **null** when the visible book cannot absorb the notional — never extrapolated.
- All money notionals are quote-currency EUR; pairs are `*/EUR`.
- Loggers `get_logger("panel.<module>")`; TDD; `uv run pre-commit run -a` gate; every commit reviewed before push; attended tasks orchestrator-only.
- The panel is `f(raw)`: any generation change regenerates the tree; never mutate rows in place.

## Reuse map

- `cli/archive/replay.py::regroup_messages(frame) -> list[dict]` (public) — the exploded-rows → WS-message inverse; `cli/archive/reader.py::canonical_segments(primary, reconciled, kind="book")`.
- `cli/capture/book.py::OrderBook(symbol, depth)` — `ingest_snapshot`/`ingest_update`; state = `bids`/`asks` dicts of `Decimal→Decimal`; ignore CRC returns.
- Atomic final + manifest: write tmp in the destination dir → `os.replace` → sidecar `"<hex>  <name>\n"` (the `cli/archive/mint.py` pattern; `verify_manifest` compatible).
- Ops role timer/runner/textfile/dead-man templates (`infra/ansible/roles/ops/templates/*-replay.*`) — copy the shape for the two new units; `LIQUIDATIONS_*` optional-channel pattern in `infra/nas/{compose.yaml,pull-entrypoint.sh}` for `PANEL_*`.

---

### Task 1: `cli/panel/primitives.py` — the pure math (TDD)

**Files:** Create `cli/panel/__init__.py`, `cli/panel/primitives.py`, `cli/panel/errors.py`; Test `tests/test_panel_primitives.py`.

**Interfaces (produces):** `PANEL_SCHEMA: dict[str, pl.DataType]` (`ts` Datetime("us","UTC"), `updates` Int64, all else Float64: `spread, spread_bps, mid, microprice, imbalance_l1, fill_bps_bid_100, fill_bps_ask_100, fill_bps_bid_1k, fill_bps_ask_1k, fill_bps_bid_10k, fill_bps_ask_10k, depth_qty_bid_l1, depth_qty_bid_l5, depth_qty_bid_l10, depth_qty_ask_l1, depth_qty_ask_l5, depth_qty_ask_l10`); `NOTIONALS_EUR = (100.0, 1_000.0, 10_000.0)`; `sample_row(bids: dict, asks: dict, *, updates: int) -> dict | None` (None on an empty side — no quotable market that second).

- [ ] **Steps 1–2 (failing tests → impl):** best bid = max bid price, best ask = min ask price; `spread = ask - bid` (assert > 0 handling: crossed/locked book → still compute, spread ≤ 0 allowed — it happens transiently); `mid = (bid+ask)/2`; `spread_bps = spread/mid*1e4`; `microprice = (ask_qty*bid + bid_qty*ask)/(bid_qty+ask_qty)`; `imbalance_l1 = bid_qty/(bid_qty+ask_qty)`. Test exact values on a hand-built book.
- [ ] **Steps 3–4:** `fill_bps`: walk the side price-ordered (asks ascending for a buy, bids descending for a sell), accumulate `price*qty` until €X; VWAP of consumed levels vs mid → bps (positive = cost). Tests: exact single-level fill, multi-level walk crossing 2 levels with a partial, shallow book → None for 10k but values for 100, empty side → row is None.
- [ ] **Steps 5–6:** `depth_qty` at levels 1/5/10 (cumulative base qty over the best-K price levels; fewer than K levels → cumulative over what exists). Decimal inputs → float outputs (floats are fine for the panel; the CRC-precision concern is raw-side only, T0045). Full suite + gate + commit `feat(panel): primitive math for the 1s L2 panel (spec 00052 Task 1)`.

---

### Task 2: `cli/panel/materialize.py` — the hour walker (TDD)

**Files:** Create `cli/panel/materialize.py`; Test `tests/test_panel_materialize.py`.

**Interfaces:** Consumes Task 1 + `regroup_messages` + `canonical_segments` + `OrderBook`. Produces `materialize_hour(path: Path, pair: str, hour: datetime, *, depth: int = 100) -> pl.DataFrame` and `materialize(primary_root, reconciled_root, panel_root, *, pair=None, since=None) -> MaterializeResult` (`MaterializeResult(hours_written: int, hours_skipped: int, rows: int, errors: list[tuple[pair, hour, str]])`); module fn `write_hour(panel_root, pair, hour, frame) -> Path` (atomic + `.sha256`); `panel_watermark(panel_root, pair) -> datetime | None` (newest existing panel hour); `write_meta(panel_root)` (`panel-meta.json`: schema_version=1, grid="1s", notionals, k_levels, code ref).

- [ ] **Steps 1–2:** `materialize_hour` on a synthetic hour (snapshot at :00 + updates at :00.5, :02.2, :02.7): rows start at second 0 (post-snapshot), the second-2 row reflects BOTH updates (`updates=2`), seconds with no messages carry the prior state (`updates=0`), 3600 rows max, ts exactly on the second grid. Pre-snapshot messages (none in a well-formed hour) and an hour whose first message is an update (no snapshot) → raise `PanelError` (the continuity invariant; verify-replay owns detecting it, the panel refuses to guess).
- [ ] **Steps 3–4:** `write_hour` atomicity (tmp never left behind on failure; `verify_manifest` passes), watermark round-trip, `materialize` sweep: only-newer-than-watermark hours processed; a corrupt hour → recorded in `errors`, sweep continues (the gap_distribution isolation pattern); reconciled-first (a healed hour's panel comes from the overlay — test with a reconciled root overriding a primary hour).
- [ ] **Steps 5–6:** full suite + gate + commit `feat(panel): hour materializer + watermarked sweep (spec 00052 Task 2)`.

---

### Task 3: `zcrypto panel materialize` CLI + README

**Files:** Create `cli/panel/command.py`; Modify `cli/__main__.py` (register a `panel` Typer sub-app), `README.md` §Usage. Test `tests/test_panel_command.py`.

- [ ] CLI: `zcrypto panel materialize PRIMARY_ROOT [RECONCILED_ROOT] --panel-root PATH [--pair] [--since]`; logs `panel materialize complete pairs=N hours_written=N hours_skipped=N rows=N errors=N`, exit non-zero iff `errors` (mirroring `verify-replay`'s contract); writes `panel-meta.json` if absent, **refuses** (clear error) if the existing meta's generation params differ from the code's (a generation change must be an explicit regeneration, not a silent mix). Tests: help, end-to-end tmp-tree run, the meta-mismatch refusal. Full suite + gate + commit `feat(panel): panel materialize command (spec 00052 Task 3)`.

---

### Task 4: Ansible — pull + materialize timers, NAS `PANEL_*` channel

**Files:** Create `infra/ansible/roles/ops/templates/{archive-pull.sh.j2,archive-pull.{service,timer}.j2,panel-materialize.sh.j2,panel-materialize.{service,timer}.j2}`; Modify `infra/ansible/roles/ops/tasks/main.yml`, `roles/ops/defaults/main.yml`, `infra/nas/compose.yaml`, `infra/nas/pull-entrypoint.sh`, `infra/nas/README.md`, `infra/ops/README.md`.

- [ ] **archive-pull timer** (hourly, :12 past): rsync the four trees from the NAS over the seed channel (`~deploy/.ssh/sync_nas_archive`, known_hosts pin, strict) — host-side rsync (no container; rsync is host-installed), textfile `ops_archive_pull_{exit_code,last_run,last_success}`, dead-man var `ops_archive_pull_healthcheck_url`.
- [ ] **panel-materialize timer** (hourly, :22 past — after the pull): the digest-pinned container runs `zcrypto panel materialize /data/capture-segments /data/capture-reconciled --panel-root /data/l2-panel`; textfile `ops_panel_{exit_code,last_run,last_success,hours}`; dead-man var `ops_panel_healthcheck_url`. Both timers `Persistent=true`, slots off boundaries/windows.
- [ ] **NAS channel:** optional `PANEL_SOURCE`/`PANEL_DEST` (default `/archive/l2-panel`)/`PANEL_SSH_KEY=/keys/sync_panel`/`PANEL_SSH_PORT` (default 22) in `infra/nas/{compose.yaml,pull-entrypoint.sh}` — copy the `LIQUIDATIONS_*` block verbatim-adapted; unset → skipped; hash-verified; reconcile gate untouched. Document both READMEs (channel setup incl. the ops-side `sync_panel` forced command pinning the panel root).
- [ ] `--syntax-check` + `bash -n` on rendered scripts + compose config parse + gate + commit `feat(config): panel + recurring-pull timers, NAS panel channel (spec 00052 Task 4)`.

---

### Task 5 **[attended]**: backfill + deploy + verify by outcome

- [ ] Image: `workflow_dispatch` on the branch; pin the default-AVX digest; pre-stage on hp; verify `zcrypto panel --help`.
- [ ] Dead-men: provision `zcrypto-archive-pull` + `zcrypto-panel` checks (hourly cadence → timeout 7200/grace 3600), vault + wire URLs.
- [ ] Channel: `sync_panel` keypair (NAS-side private, ops-side forced command pinning `/var/lib/zcrypto-ops/l2-panel`), NAS `.env` `PANEL_SOURCE`, ship updated compose/entrypoint **re-applying the digest pin** (the deployed compose is digest-pinned; re-pin after any file ship — the 2026-07-15 lesson).
- [ ] Converge with the digest → **backfill run** (`panel materialize` over all seeded hours; measure the rate, parallelize only if needed) → verify: per-pair panel hours ≈ canonical hours, manifests verify, spot-check a BTC hour's spread against a hand-computed value from the raw segment, **the first-look per-pair spread table** (median/p90 spread_bps — the verification-by-outcome), timers armed, dead-men green, NAS mirror pulls the panel tree.

---

### Task 6: Closeout

- [ ] `docs/iterations-history-phase1.md` entry (iter-098 — the panel is data-foundation subject matter); T0033 OPS-4 → done (next steps trim to OPS-5/6); T0014 `## Findings so far` gains "the panel exists — calibration is a one-query start" (topic stays open: the calibration itself is its remainder); index syncs; deferral sweep; commit `docs(infra): OPS-4 closeout (iter-098)`.

## Self-review

Spec coverage: D1/D2 → Task 1; D3 → Task 2 (canonical, snapshot-anchored, honest gaps); D4 → Task 2 `write_hour`; D5 → Tasks 2/3 (meta + refusal); D6 → Task 4 timers + watermark in Task 2; D7 → Task 4 NAS channel; D8/D9 → Task 5. Type consistency: `PANEL_SCHEMA`/`sample_row`/`materialize_hour`/`write_hour`/`panel_watermark` named identically across tasks. No placeholders; attended steps in Task 5 only.
