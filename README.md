![Version](https://img.shields.io/badge/version-v0.0.0-blue)
![GitHub License](https://img.shields.io/github/license/zhaow-de/zcrypto-kraken)
![Python Version from PEP 621 TOML](https://img.shields.io/python/required-version-toml?tomlFilePath=https://raw.githubusercontent.com/zhaow-de/zcrypto-kraken/develop/pyproject.toml)
![Coveralls](https://img.shields.io/coverallsCoverage/github/zhaow-de/zcrypto-kraken)
![healthchecks.io](https://img.shields.io/endpoint?url=https%3A%2F%2Fhealthchecks.io%2Fbadge%2F32eaee6f-cb82-4773-9471-4b802136adc1%2FopNhEK_4-2.shields)

# zcrypto

Learning-for-Fun quant-trading research project for Kraken (spot + spot-margin).

<!-- mdformat-toc start --slug=github --maxlevel=4 --minlevel=2 -->

- [Requirements](#requirements)
- [Usage](#usage)
  - [`zcrypto capture`](#zcrypto-capture)
  - [`zcrypto liquidations`](#zcrypto-liquidations)
  - [`zcrypto liquidations-poll`](#zcrypto-liquidations-poll)
  - [`zcrypto engine`](#zcrypto-engine)
    - [Shadow soak service (systemd user unit)](#shadow-soak-service-systemd-user-unit)
    - [VPS journal pull and daily gate ops — retired (moved to the NAS)](#vps-journal-pull-and-daily-gate-ops-%E2%80%94-retired-moved-to-the-nas)
  - [`zcrypto archive`](#zcrypto-archive)
  - [`zcrypto panel`](#zcrypto-panel)
  - [`zcrypto data`](#zcrypto-data)
  - [`zcrypto research`](#zcrypto-research)
  - [`zcrypto tick`](#zcrypto-tick)
- [Configuration](#configuration)
  - [`[zcrypto]`: dataset paths](#zcrypto-dataset-paths)
  - [`[zcrypto.engine]`: shadow-engine settings](#zcryptoengine-shadow-engine-settings)

<!-- mdformat-toc end -->

## Requirements<a name="requirements"></a>

- **Python 3.14** (pinned in `.python-version`).
- **[uv](https://docs.astral.sh/uv/)** — run `uv sync` to install/refresh the locked environment.

## Usage<a name="usage"></a>

```bash
zcrypto [OPTIONS]          # or: uv run python -m cli [OPTIONS]
```

| Option | Description |
| -- | -- |
| `-v`, `--version` | Show the application version and exit. |
| `-l`, `--log <path>` | Append JSONL logs to this file. If unset, plain-text logs go to stdout. |
| `--log-level {DEBUG,INFO,WARNING,ERROR}` | Log threshold (default `INFO`). Applies to the `zcrypto.*` loggers. |
| `--ship-logs` | Also ship logs to Grafana Cloud Loki, in addition to stdout/file. Requires `ZCRYPTO_LOKI_URL`, `ZCRYPTO_LOKI_USERNAME`, `ZCRYPTO_LOKI_PASSWORD`, `ZCRYPTO_LOG_HOST`, `ZCRYPTO_LOG_SERVICE` (exits with an error naming every missing one if any is unset or empty). |
| `-h`, `--help` | Show help and exit. |

Running `zcrypto` with no options (or with `-h` / `--help`) prints the help.

Log shipping is additive — it never replaces the stdout/file handler — and never blocks the app: records are buffered in a bounded ring and shipped from a background thread, dropping the oldest lines rather than buffering unboundedly when Loki is unreachable.

Setting the `ZCRYPTO_METRICS_PORT` env var starts a Prometheus `/metrics` HTTP exporter on that port for `capture`, `engine run`, and `liquidations-poll` (process self-metrics plus each daemon's own application series). It is opt-in: unset means no exporter at all, and a non-integer value logs an error and runs without one — a metrics misconfiguration never stops a daemon.

### `zcrypto capture`<a name="zcrypto-capture"></a>

24/7 daemon that streams Kraken's **public** WS v2 feed (no API keys) — order book (depth 100) + trades — for the universe pairs, and writes hourly zstd-compressed Parquet segments (with a `.sha256` manifest per segment) for later backfill/analysis.

```bash
zcrypto capture [OPTIONS]
```

| Option | Description |
| -- | -- |
| `--pairs <PAIR>` | Pair to capture, e.g. `--pairs BTC/EUR`; repeat for multiple. Defaults to the EUR majors in the newest `data/universe-<stamp>/point-in-time-universe.json`; if no stamped set is present the command fails rather than reading the frozen unstamped one. |
| `--depth <INT>` | Order book depth: one of `10`, `25`, `100`, `500`, `1000` (default `100`). |
| `--data-dir <PATH>` | Segment output base directory. Defaults to `$ZCRYPTO_CAPTURE_DATA_DIR` if set, else `/var/lib/zcrypto-capture/segments`. |
| `--duration <SECS>` | Run for this many seconds then stop cleanly (for smoke-testing); omit to run until interrupted. |

Segments land at `<data-dir>/<pair>/{book,trades}/<YYYY>/<MM>/<DD>/<HH>.parquet`. Set `HEALTHCHECK_URL` (a healthchecks.io ping URL) to enable the dead-man's-switch liveness ping; it's optional and skipped when unset.

### `zcrypto liquidations`<a name="zcrypto-liquidations"></a>

**Shelved in place**: a daemon that streams Binance USD-M futures **liquidation** (`forceOrder`) events from the keyless combined stream `wss://fstream.binance.com/stream?streams=!forceOrder@arr` (no API keys) and writes hourly zstd-compressed Parquet segments (with a `.sha256` manifest per segment), one per symbol, reusing the capture `SegmentWriter`. It is **not deployed**: Binance geo-fences its futures WS from our network egresses, so the deployed feed is `liquidations-poll` below; the code stays tested and portable in case a served egress ever materializes.

```bash
zcrypto liquidations [OPTIONS]
```

| Option | Description |
| -- | -- |
| `--data-dir <PATH>` | Segment output base directory. Defaults to `$ZCRYPTO_LIQUIDATIONS_DATA_DIR` if set, else `/var/lib/zcrypto-ops/liquidations`. |
| `--duration <SECS>` | Run for this many seconds then stop cleanly (for smoke-testing); omit to run until interrupted. |

Segments land at `<data-dir>/<SYMBOL>/liquidations/<YYYY>/<MM>/<DD>/<HH>.parquet` (`<SYMBOL>` is the Binance ticker, e.g. `BTCUSDT`), with columns `ts, symbol, side, price, orig_qty, avg_price, order_status, event_id`. Redelivered events (Binance replays force-orders on reconnect) are de-duped on the synthesized `event_id`. Set `LIQUIDATIONS_HEALTHCHECK_URL` (a healthchecks.io ping URL) to enable the dead-man's-switch liveness ping; it's optional and skipped when unset.

### `zcrypto liquidations-poll`<a name="zcrypto-liquidations-poll"></a>

The deployed fallback for `zcrypto liquidations` above: Binance geo-fences its futures WS from every egress we own, so this polls Coinalyze's REST `/v1/liquidation-history` endpoint every `$COINALYZE_POLL_SECONDS` (default 300s) for the funding basket's 10 USDT perps (`<COIN>USDT_PERP.A`, one batched call per cycle) and writes closed 1-min liquidation buckets to hourly zstd-compressed Parquet segments (with a `.sha256` manifest per segment), one per coin, reusing the capture `SegmentWriter`. It shares the data dir with `zcrypto liquidations` (the single-instance lock keeps both from writing at once); liquidations are not backfillable, so the segment tree replicates to the NAS.

```bash
zcrypto liquidations-poll [OPTIONS]
```

| Option | Description |
| -- | -- |
| `--data-dir <PATH>` | Segment output base directory. Defaults to `$ZCRYPTO_LIQUIDATIONS_DATA_DIR` if set, else `/var/lib/zcrypto-ops/liquidations`. |
| `--duration <SECS>` | Run for this many seconds then stop cleanly (for smoke-testing; runs at least one poll cycle even with `0`); omit to run until interrupted. |

Requires `$COINALYZE_API_KEY` (exits with an error if unset). Segments land at `<data-dir>/<COIN>/liquidations-1m/<YYYY>/<MM>/<DD>/<HH>.parquet`, with columns `ts, symbol, long_usd, short_usd, event_id`. Only buckets Coinalyze has proven closed (`bucket_end <= now - 120s`) are ingested; each cycle re-polls the last 24h and relies on the synthesized `event_id` (`<symbol>-<bucket_start>`) for de-dup, since Coinalyze's own history only stretches back ~25-33h. Set `LIQUIDATIONS_HEALTHCHECK_URL` (a healthchecks.io ping URL) to enable the dead-man's-switch liveness ping (sent only after a fully successful cycle); it's optional and skipped when unset.

### `zcrypto engine`<a name="zcrypto-engine"></a>

The shadow trading engine: a live price store seeded from the canonical dataset and kept warm by Kraken REST gap-fills, a Nautilus node that runs one shadow cycle per 4h UTC boundary (00/04/08/12/16/20), a per-day journal of cycle evidence (records, failed-cycle sidecars, input snapshots, `orders.jsonl`), and replay/report verification against the ratified concordance gate. Settings come from the [`[zcrypto.engine]`](#zcryptoengine-shadow-engine-settings) table.

```bash
zcrypto engine <subcommand> [OPTIONS]
```

| Subcommand | Description |
| -- | -- |
| `seed` | Seed/refresh the live price store (`store_dir`) from the canonical dataset (`data/ohlc-full`) plus a REST gap-fill; idempotent, prints the per-pair × grid seam-QA summary (overlap bars, appended/replaced counts). Also the documented repair for a poisoned store tail. |
| `run` | Run the shadow TradingNode in the foreground — one journaled cycle per 4h boundary (the soak's systemd user service runs this). Fails fast (exit 1) when the store is missing/empty, or when `ZCRYPTO_REQUIRE_CONFIG` is set and no `zcrypto.toml` exists; a startup watchdog force-exits if the trader is not running once the node's connect + reconcile timeouts (+ 30 s) lapse — the supervisor's restart is the recovery. Set `HEALTHCHECK_URL` to enable the per-cycle dead-man's-switch ping (success record → the URL, failed-cycle sidecar → `<url>/fail`; a propagating exception pings nothing and alerts by silence). |
| `cycle [--at ISO_TS] [--replace]` | Run one cycle manually. Defaults to the most recent elapsed boundary; `--at` must be an aware ISO-8601 timestamp exactly on the 4h UTC grid. A boundary that already has a record/sidecar is refused unless `--replace` (which deletes both artifacts plus the boundary's snapshots first). Exits non-zero when the cycle fails. |
| `replay [--date YYYY-MM-DD] [--path fast\|verified] [--journal-dir <PATH>]` | Replay journaled success cycles through the builder and compare recomputed targets against the journaled ones. Hash mismatches and validation failures are classified per cycle (the sweep never crashes), sidecars are listed as failed cycles, and any mismatch/validation failure exits non-zero. `--journal-dir` reads a journal other than the configured one (e.g. a pulled VPS journal). |
| `report [--journal-dir <PATH>]` | Rebuild every journaled cycle outcome by replay-on-demand (fast path) and evaluate the ratified ≥ 14-clean-day gate: prints streak length, gate status, and the most recent failure. Absent boundaries are scored missing, never fabricated. `--journal-dir` reads a journal other than the configured one. |
| `gate-export --textfile <PATH> [--journal-dir <PATH>] [--healthcheck-url <URL>] [--lag-fail-seconds <SECS>] [--cache <PATH>]` | Evaluate the gate (same replay-on-demand pass as `report`) and atomically write it as a Prometheus node-exporter textfile, then ping an independent dead-man's-switch healthcheck. Emits `zcrypto_gate_status` (1/0), `zcrypto_gate_streak_days`, `zcrypto_gate_journal_pull_lag_seconds` (omitted when the journal is empty), `zcrypto_gate_mismatch_total` (every not-clean cycle: replay mismatches + validation failures + failed-cycle sidecars), `zcrypto_gate_cache_replayed`, `zcrypto_gate_cache_hits` (per-run gauges, no `_total` suffix), `zcrypto_gate_cache_invalidated` (1/0), `zcrypto_gate_cache_oldest_verification_age_seconds` (omitted when the cache is inactive or empty), `zcrypto_gate_export_duration_seconds` (wall time to evaluate the journal; excludes writing the textfile and the healthcheck ping), and `zcrypto_gate_export_timestamp_seconds`. `--healthcheck-url` pings clean (GET the URL) iff `mismatch_total == 0` and the journal-pull lag is within `--lag-fail-seconds` (default `21600`, 6h); otherwise pings `<url>/fail`. Omit `--healthcheck-url` to skip the ping. `--cache <PATH>` reuses a prior run's replay outcome for any cycle whose journaled evidence is unchanged, so only new cycles are replayed; omit it for today's full replay every run (byte-identical outcome either way — the cache metrics still emit, zeroed). When the cache is active, each run additionally force-replays a deterministic ~1/24 rotating slice of otherwise cache-eligible cycles regardless of a fingerprint hit, so the whole journal's parquet bytes are re-verified about daily even with the cache warm — a forced re-verification that fails is a real gate failure (counted as `replayed`, never `from_cache`), not a cache event. A mismatch outcome is itself cached, so after repairing corrupted journal evidence, delete the cache file so the next run re-verifies immediately rather than serving the cached mismatch for up to a rotation. Exits 0 even when the gate has a mismatch or is stale (those are findings, surfaced via the metrics/ping); non-zero only on an operational failure (unreadable journal, unwritable textfile). |
| `soak-check [--journal-dir <PATH>] [--store-dir <PATH>] [--canonical-dir <PATH>] [--registry <PATH>] [--fee-per-side <RATE>] [--band <FLOAT>] [--floor <N>] [--null windows\|block-bootstrap\|both] [--path fast\|verified] [--json <PATH>]` | Compare the realized shadow-engine journal against a backtest null rebuilt from the frozen canonical dataset: judges 7 structural metrics (gross/net/active_frac/turnover/hhi/governor_engagement/cap_breach — the last two recovered by a one-time internals rebuild off the newest journaled cycle's snapshots), the governor-bias (governed-vs-live) gap, and non-gating P&L, plus interpretive disclosures that change no verdict. `--canonical-dir` defaults to `data/ohlc-full`; when it's absent, or the scored window is shorter than `--floor` (default `30`), or a self-test fails, or the internals rebuild succeeded but its identity/cap-consistency proof failed, the report prints "NO VERDICT" and suppresses the per-metric table rather than a false conclusion (a self-test that ran and failed also exits non-zero — a short/void window still exits 0). An internals rebuild that could not run at all (missing/corrupt snapshots, a builder error) instead degrades governor_engagement/cap_breach to "n/a" without voiding the run. The report also states **what bounded the scored window** — `window_bound` in the realized-series block and in the JSON provenance: `journal` when the window ran to the end of the journal's contiguous cycle segment (the benign case: the last cycle never scores, so one dropped cycle is normal), `store` when the price store's last usable bar predates the journal and truncated the window, `clock` when the trailing cycles' successors have not happened yet. A store-bound window prints a warning above the verdict table naming the store's last usable bar, the journal's last cycle, and how many cycles the gap cost; the run still completes and still scores what it can (reading a deliberately partial store is legitimate), but its numbers are a read on a stale window rather than on the journal's current extent — point `--store-dir` at a store that covers the journal to widen it. `--null` (default `both`) picks which backtest null construction(s) judge each metric: `windows` (the overlapping-window reference, reproducing the pre-`--null` verdicts byte-for-byte), `block-bootstrap` (an independently resampled reference), or `both`, which judges under each and reconciles the two verdicts — agreement keeps the shared label, a mild disagreement takes the milder one, and an outright `consistent`-vs-`inconsistent` split degrades to `indeterminate (instrument-fragile)` rather than asserting more than the two constructions agree on; the report's `verdict`/`primary`/`secondary` columns (the reconciled label and each null's own raw label — both raw labels are always recoverable as their own column, so agreement and disagreement are always distinguishable) and multiplicity line surface this. `--path` (default `fast`) selects the builder for the null rebuild and the identity self-check: `fast` or the much slower `verified` oracle rebuild, for re-reading a suspicious result without editing code. `--registry` is the trial-registry JSON-lines file the instrument self-test reproduces the ratified record against. `--json` writes the full payload atomically. Read-only decision-support — never a validation exercise, never the concordance gate — and it consumes no holdout budget. |
| `decompose [--journal-dir <PATH>] [--since YYYY-MM-DD] [--until YYYY-MM-DD] [--json]` | Attribute each journaled cycle's gross across the pipeline stages — per-sleeve gross → combined → capped → governed final, plus the ratio between each consecutive pair, so a shrinking book has a named cause rather than an observed drop. Every intermediate stage is recomputed from public builder parts and then proven twice per cycle: against the in-process build (`multiplier × capped == final_targets`, exactly) and against the journaled `final_targets`, so a builder change or a rebuild that diverges from what the engine actually traded surfaces as a named failure instead of a silently wrong table. Each summary ratio is the median of the per-cycle ratios, never a ratio of medians. `--since`/`--until` bound the UTC day window (both inclusive). A cycle record that cannot be parsed aborts the run; one that parses but fails to replay is named and counted in the output and exits non-zero — a silently dropped cycle would bias every aggregate. `--json` emits the full payload on stdout instead of the table, with non-finite values (a flat cycle's 0/0 cancellation ratio) as `null`, so the output is always valid JSON. Read-only. |
| `accum-replay [--journal-dir <PATH>] [--since YYYY-MM-DD] [--until YYYY-MM-DD] [--minimums <PATH>] [--nav <EUR>]… [--json]` | Measure the position drift the venue's order minimums impose at each portfolio size: replays an accumulate-until-placeable policy over the journaled targets, carrying held state in base units priced at each cycle's journaled close, and placing only when the delta clears both `ordermin` (a quantity) and `costmin` (euros) — independent gates, never a max over mixed units. Drift is measured after the placement decision, in bps of NAV: per-cycle median and p95 over the whole window, plus a per-ISO-week mean carrying each week's cycle count and a partial-week flag. There is deliberately no weekly p95 — a handful of weeks cannot support a percentile — and NAV is held constant across the window so the number stays a pure placement floor rather than folding in P&L. `--nav` is repeatable and defaults to 500/1,000/2,500/5,000/10,000 EUR. `--minimums` defaults to the newest `kraken-refdata-*.json` under `<data_dir>/snapshots`; that snapshot's `fetched_at` stamp is printed beside the drift table, because these floors move and a band quoted from an older table is stale rather than conservative. Unparseable and unreplayable records behave exactly as in `decompose`. `--json` emits the payload with non-finite values as `null` and the per-NAV table keyed by each NAV's string form (every row also carries its numeric `nav`). Read-only. |
| `tracking-report [--journal-dir <PATH>] [--since YYYY-MM-DD] [--until YYYY-MM-DD] [--nav <EUR>] [--gate-from YYYY-Www] [--minimums <PATH>] [--simulated-fills] [--ledger-export <PATH>] [--json]` | Compare each ISO week's **realized** drift — the position the journaled fills actually built — against the venue-minimum drift floor `accum-replay` measures over the same cycles, and reprice the traded cost from the same fills. Per ISO week: the floor's p95 over that week's cycles, the realized mean, and whether the realized mean sits within the floor. A week is **decided** only when it is complete, sits on or after the gate boundary, and does not straddle the first fill; the reason a week is not decided is named in its own column rather than left to be inferred, and the overall verdict stays `insufficient-data` until at least 3 weeks are decided. **`--gate-from YYYY-Www` names the first ISO week that counts** — absent it, **no** week is decided whatever the numbers say, because a week nobody has declared in-scope must not be able to produce a pass; the report says so and names the flag, and every week's floor p95 and realized mean are printed either way, since only the verdict is withheld. `--nav` is **single-valued** (unlike `accum-replay`'s repeatable sweep: that command explores a curve, this one issues one verdict) and defaults to the configured `engine.shadow_nav_eur`, which is the size the engine itself trips at — so the size a human bands at cannot drift from the size the engine acts on. The compared NAV is printed on the `Verdict:` line. The cost block reports the notional-weighted maker/taker split of the **priceable** book (a fill the venue gave no liquidity side for is counted but has no side to split), the realized fee per side against the currently assumed one, and the per-fill min/median/max spread rather than a standard deviation. `--minimums` behaves exactly as in `accum-replay`, and its `fetched_at` stamp is printed above the table. `--simulated-fills` replaces the journaled fills with the drift floor's own modelled placements at each journaled close, so the whole comparison can be exercised before a single real fill exists; the report is labelled, and the fees it models come from the assumed maker rate, so that run's cost blend can recalibrate nothing. **`--ledger-export <PATH>` reconciles the window against a Kraken ledger export** (History → Export → Ledgers), the hand-made artifact that carries the one cost no fill can: the venue charges a margin position's **rollover** against the POSITION, so it appears in no execution record and a cost basis built from fills alone omits it. The reader is header-driven and **refuses an export whose header lacks a column it needs, naming the column** — the format is an assumption until a real export has been read, so a changed one must fail loudly rather than parse into a confidently wrong number. A `trade` row whose venue trade id matches no journaled fill is account activity this journal does not know about: it **fails the reconciliation, not the run** — every unmatched id is named, the drift half still prints so the numbers to investigate with are in hand, and the exit code is non-zero so no script reads a failed reconciliation as a pass. **A failed reconciliation also withdraws `cost.proposed_fee_per_side`** (it reads `null`, and `cost.basis` names the unmatched count): the measured blend stays, but the number this comparison exists to feed into a config is not published over a book the ledger could not reconcile, since a `--json` consumer reads that key without ever looking at `n_failed`. Rollover rows are summed as a euro cost only when the row's asset is a euro (both venue spellings). Only `trade` rows are matched today, so any row type the reader places nowhere — `margin` above all, which a margin position writes carrying its trade's id — is **counted by type and printed** rather than passed over silently, and the block reports how many rows were read at all, so "read nothing" cannot read as "found nothing". Combined with `--simulated-fills` the block is a guaranteed failure (a modelled fill carries no venue trade id) and says so. Absent the flag the report simply omits the block. Unparseable and unreplayable records behave exactly as in `decompose`; an execution record that cannot be read aborts, because its fills move the position every later cycle is measured against. `--json` emits the payload with non-finite values as `null`. Read-only. |
| `exec-status [--state-dir <PATH>]` | Report whether the engine may submit orders right now, and every input that decided it: the arming keys (config flag + arm file), the kill switch, the restart hold, and the last venue reading — each printed separately, because the published `zcrypto_exec_gate_level`/`zcrypto_exec_armed` gauges carry only a number and conflate their two arming keys, never the reasons. Prints `level=<none\|reduce_only\|full>`, `reasons=<comma-separated, or "-">`, then every gate input on its own line. `--state-dir` reads the control files from a directory other than the configured `journal_dir`'s parent. Read-only — mutates nothing. |
| `probe-plan <PATH> --check` | Validate an operator-authored probe plan offline before it is placed: plan shape, expiry, duplicate plan ids against the execution ledger, the plan-level notional cap and margin floor, each intent's floors against the newest journaled venue snapshot, and the current gate verdict. Advisory only — the engine re-validates every plan live before any order; a plan is placed by staging it under another name in the engine state directory and **renaming** it onto `exec/probe-plan.json`, never by writing that path in place — the executor reads it every five seconds, so a half-written file is refused and deleted. Only the account owner places a plan, following the `engine-probe-window` procedure in `infra/runbooks/engine.md`. Exits non-zero on any refusal. Read-only — mutates nothing. |

#### Shadow soak service (systemd user unit)<a name="shadow-soak-service-systemd-user-unit"></a>

`infra/systemd/zcrypto-engine-shadow.service` is a systemd **user**-unit template that keeps `zcrypto engine run` alive on a workstation (`Restart=on-failure`, `RestartSec=30`, `WantedBy=default.target`). Fill in its `<repo>`/`<uv>` placeholders (absolute paths), then:

```bash
loginctl enable-linger $USER            # prerequisite: without lingering the user service dies on logout
loginctl show-user $USER -p Linger      # verify: prints Linger=yes
mkdir -p ~/.config/systemd/user
cp infra/systemd/zcrypto-engine-shadow.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now zcrypto-engine-shadow.service
systemctl --user status zcrypto-engine-shadow.service    # confirm: active (running)
```

#### VPS journal pull and daily gate ops — retired (moved to the NAS)<a name="vps-journal-pull-and-daily-gate-ops-%E2%80%94-retired-moved-to-the-nas"></a>

**Retired.** The daily gate ops (journal pull → verified replay → report) ran on the workstation as a systemd `--user` timer; it lagged whenever the workstation was offline. It is superseded by the always-on NAS gate-verify tier — the `archive-pull` container pulls the journal and runs `zcrypto engine gate-export` (fast-path gate scoring, emitted to Grafana + a dead-man ping) on every cycle (spec `docs/specs/00049-role-b-nas-gate-verify-design.md`, `infra/nas/`). The `infra/systemd/zcrypto-engine-gateops.{service,timer}` templates are removed.

On a workstation that still has the old timer installed, disable it:

```bash
systemctl --user disable --now zcrypto-engine-gateops.timer
rm -f ~/.config/systemd/user/zcrypto-engine-gateops.service ~/.config/systemd/user/zcrypto-engine-gateops.timer ~/.ssh/zcrypto-sync_ed25519
systemctl --user daemon-reload
```

### `zcrypto archive`<a name="zcrypto-archive"></a>

The always-on NAS pull/archive tier: pull a source tree via rsync-over-ssh, then hash-verify every segment against its `.sha256` manifest sidecar.

```bash
zcrypto archive pull <source> <dest>
```

| Argument | Description |
| -- | -- |
| `source` | rsync source spec, e.g. `deploy@host:/var/lib/zcrypto-capture/segments/`. |
| `dest` | Local destination directory to rsync into and verify. |

`pull` exits **2** on an rsync transport failure (a partial pull is never verified as authoritative — this also covers a missing `ARCHIVE_SSH_KEY`), **1** if any pulled segment fails its manifest hash check, else **0**. The rsync-over-ssh transport reads `ARCHIVE_SSH_KEY` (the private key path, required), `ARCHIVE_SSH_PORT` (default `10022`), and `ARCHIVE_SSH_KNOWN_HOSTS` (a `UserKnownHostsFile` path). Host-key checking is strict (`StrictHostKeyChecking=yes`), so `ARCHIVE_SSH_KNOWN_HOSTS` must be pre-seeded with the remote host key — an unknown or changed key fails the pull closed rather than trusting it.

`reconcile` reads the two raw capture mirrors and mints healed hours into a separate overlay root, leaving both mirrors immutable and canonical-by-default.

```bash
zcrypto archive reconcile <primary_root> <secondary_root> <reconciled_root>
```

| Argument / Option | Description |
| -- | -- |
| `primary_root` | The primary mirror (raw, canonical-by-default). |
| `secondary_root` | The secondary mirror (raw). |
| `reconciled_root` | The overlay: only healed hours are minted here. |
| `--window-hours` | Trailing settled hours to re-scan each cycle (default `48`). |
| `--min-gap-seconds` | Primary book silence longer than this, with the secondary alive inside it, is a gap (default `30`). |
| `--textfile` | Prometheus textfile to publish (`reconcile.prom`). Omit to export nothing. |
| `--mint` / `--detect-only` | **Default `--detect-only`**: ledger what *would* be spliced and mint nothing. |

**`--detect-only` is the safe default; the deployed reconciler runs `--mint` since 2026-07-17.** The phantom-splice concern that kept minting locked is now measured, not feared: a 66 h cross-host soak (217 windows, max 12.08 s — a hand-classified per-connection coalescing artifact) validated `--min-gap-seconds 30` (2.48× the worst artifact, 2.8× below the smallest real outage), and a live two-leg drill healed a real 25-minute primary outage exactly (one secondary block, CRC-clean replay across both splice boundaries) while a deliberately healthy hour minted nothing. Detect-only remains the default for ad-hoc runs: it ledgers every `would_mint` and writes no parquet.

An hour is considered once `now ≥ H + 2h` (finalization plus one pull cycle have both had time to land), and a hour still missing from the primary past `H + 6h` is minted from the complete secondary alone. Healing is **whole-window** for books (a secondary block is spliced in, never row-interleaved — L2 rows carry absolute quantities) and **row-level** for trades (`trade_id` is globally unique across hosts). Every decision is appended to `<reconciled_root>/reconcile-ledger.jsonl` (states `minted`, `would_mint`, `trade_deficit`, `both_streams_silent`, `total_loss`, `unwitnessed`, `failed`) — `unwitnessed` is primary silence no secondary *update* covers, so it cannot be healed; it is recorded for visibility and deliberately feeds no counter, since the fleet-wide record already books those seconds whenever the fleet was dark, and each minted final gets a `.sha256` sidecar plus an `<HH>.provenance.json`, so the overlay verifies with the same `verify_tree` as a raw mirror.

Two **correlated-loss** detectors run regardless of the flag and never mint: `both_streams_silent` (every pair silent on *both* hosts in the *same* window — at depth 100 that has no benign explanation) and `total_loss` (an hour absent from both mirrors while real data brackets it on either side). When both streams are dark there is no witness to heal with, so the loss is permanent: it is ledgered, booked into `zcrypto_reconcile_residual_gap_seconds_total`, and paged.

**The counters describe the minted output, not the window that admitted it.** A gap is admitted on a single secondary `update` row anywhere inside it — which admits a window without filling one — so `zcrypto_reconcile_healed_gap_seconds_total` is re-measured against the hour actually minted, and whatever the splice left unfilled joins `zcrypto_reconcile_residual_gap_seconds_total`, minus any second a `both_streams_silent` record already booked for the same stream (every second of loss is attributed exactly once). The ledger record keeps the admitting window as `claimed_seconds`, and that — not the measured heal — is what `zcrypto_reconcile_healable_gap_seconds_total`, the degrading-primary rate, stays denominated in.

`reconcile` exits **2** when a mirror is unreadable (transport), **1** on an integrity failure (an unreadable segment, a non-monotonic stream, a corrupt ledger — no textfile is published, so `last_success_timestamp` goes stale and pages), else **0**. Residual gaps are a *finding*, not a failure: they exit 0 and page through the metric.

`verify-replay` continuity-replays every canonical book hour — reconciled-first, primary otherwise — through the capture `OrderBook` and reports four per-hour checks: **anchored** (**chain-anchored**: the hour opens with a `type=snapshot` message, OR its exact predecessor hour for the same pair was present in the replayed set and was itself anchored and error-free; Kraken snapshots arrive on subscribe, not once per capture hour, so most real hours open with plain updates and rely on this chain), **ts-ordered** (rows non-decreasing in `ts`), **checksum-present** (every message carries its capture-time `checksum` attestation), and **replay-ok** (the rows regroup into WS-shaped messages and ingest without a structural throw). It never re-derives the CRC: the archive stores `price`/`qty` as Float64, so Kraken's checksum is not byte-exactly reproducible — the stored column is trusted as capture-time ground truth.

```bash
zcrypto archive verify-replay <primary_root> [reconciled_root]
```

| Argument / Option | Description |
| -- | -- |
| `primary_root` | The primary mirror (raw, canonical-by-default). |
| `reconciled_root` | Optional healed overlay; its hours replay reconciled-first. Omit to replay the primary alone. |
| `--pair` | Only this pair (e.g. `BTC/EUR`). Defaults to every pair. |
| `--since` | Only hours at/after this UTC date (`YYYY-MM-DD`). |
| `--depth` | Book depth the archive was captured at (default `100`, capture's default); the replayed book prunes to it. |
| `--state-dir` | Cache verified hours here and replay only the changed ones on later runs. Reports a census and only the currently-failing hours instead of a line per hour. Cannot be combined with `--pair`/`--since`. |
| `--reverify-all` | Replay every hour again and refresh the whole cache, ignoring what it already holds. Requires `--state-dir`. |
| `--drain-budget-seconds` | Wall-clock budget for re-verifying cached hours whose bytes changed (default `7200`). Whatever does not fit is reported as `pending` and picked up by the next run. Applies only with `--state-dir`; without it there is no drain and the value is ignored. |
| `--audit-sample` | How many hours served from the cache to replay again and compare against it each run (default `25`). A disagreement fails the run. Applies only with `--state-dir`; without it nothing is served from cache and the value is ignored. |

One line per hour plus a summary; a bad hour is isolated into its own result (the sweep never aborts). Exits **1** if any hour errs or fails any of the four checks, else **0**.

`--state-dir` switches on the **incremental** path the nightly runner uses. Each hour's raw per-hour facts are checkpointed against the sha256 of the bytes replayed, so an unchanged hour is served from `<state_dir>/checkpoint.parquet` instead of re-replayed; the chain-anchoring fold is recomputed over cached and fresh verdicts alike on every run, so the report still describes the whole archive and a rewritten hour can still un-anchor its successors. Hours never seen before are always replayed; hours whose bytes changed drain oldest-first until `--drain-budget-seconds` is spent, and the remainder is announced as `pending`. Output becomes a census plus one line per **currently-failing** hour plus the same summary:

```
verify-replay census replayed=288 reused=5712 audited=25 mismatches=0 pending=0 evicted=0 duration_s=1381
<ts> INFO zcrypto.archive.command … - verify-replay census replayed=288 reused=5712 audited=25 mismatches=0 pending=0 evicted=0 duration_s=1381
replayed 6000 hour(s): 6000 ok, 0 failed
<ts> INFO zcrypto.archive.command … - verify-replay complete hours=6000 ok=6000 failed=0
```

Four lines, in that order. The logger's handler writes to stdout alongside `echo`, so the census appears twice — verbatim as plain output, then again through the logger — and the summary appears as a pair of differently-worded twins, `replayed N hour(s)` echoed and `verify-replay complete hours=…` logged. The logged forms are the machine-readable ones: the runner parses `hours=`/`failed=` out of `verify-replay complete`, and the census fields out of the logged census line.

Three conditions exit **2 with the summary withheld**, so the runner's `ops_verify_replay_run_ok` reads 0 and the run-broken rule pages rather than the run reading healthy: the checkpoint could not be written, the enumeration lost more than a tenth of the checkpointed hours (an unmounted mirror, not a real shrink — past a *deliberate* mass shrink, delete the state directory and accept the announced rebuild), or a sampled audit found an hour disagreeing with the verdict the cache served for it. The audit-mismatch case is the one that still prints its census, so `mismatches=` is what tells it apart from a crash — the runner publishes that count as `ops_verify_replay_audit_mismatches`, and it is the only census field it takes from a run whose summary was withheld. An empty enumeration likewise emits neither census nor summary — it takes the existing `no canonical book hours found` path, since `hours=0 ok=0 failed=0` would parse as a healthy sweep of an unmounted NAS.

`backfill-trades` heals the canonical trade stream to a contiguous, duplicate-free sequence of trade ids. It re-reads a pair's settled trade hours from the archive, detects any missing or duplicated ids, fetches the missing ones from Kraken's public REST, and mints the healed hours into the reconciled overlay — never fabricating a trade: an id the REST endpoint will not serve stays absent from the output.

```bash
zcrypto archive backfill-trades <primary_root> <reconciled_root>
```

| Argument / Option | Description |
| -- | -- |
| `primary_root` | The primary (raw) canonical trade archive. |
| `reconciled_root` | The overlay healed hours are minted into. |
| `--pair` | Only this pair (e.g. `BTC/EUR`). Defaults to every pair. |
| `--detect-only` | Report the loss; mint nothing. |

The summary line reports what the sweep **found** and, separately, what it **healed** — the two are different questions and both are printed, so a run can never read as clean by omitting one. Found: `pairs` swept, `gaps` found, `trades_missing` (how many trade ids are absent — the loss magnitude), and `duplicate_rows_found`. Healed, and every outcome bucket a fetched or existing row can land in: trades `recovered` (**only what was actually written**), trades `unrecoverable` (missing ids the REST would not serve — left absent, never invented), trades `deferred` (fetched, but their hour hasn't settled yet, so a later run lands them), trades `fetch_failed` (ids in gaps whose fetch itself raised — the failure is totalled here, and the per-gap warning carries the details), trades `mint_failed` (rows the REST served for an hour whose *mint* then raised — retryable, so the next run re-detects and re-fetches them; deliberately **not** subtracted from the post-mint accounting check, which must still trip loudly on the failure), `duplicates_collapsed` (repeated ids removed within one hour), `duplicates_cross_hour` (repeated ids split across two hour files, which a per-hour mint cannot collapse), `hours_minted`, `hours_repaired_after_loss` (settled hours this run successfully minted that had **no** trades final while a *book* final **spanning** the same hour did — the signature of a genuinely lost trades segment, which the sweep repairs; without it the repair is silent and a real loss event leaves no operator-visible trace, since an hour in which a quiet pair simply printed nothing writes no file either. The witness must span the hour, not merely exist: a capture restart mid-hour leaves a book final too, and the pair being quiet across the connected part is not a loss), and `errors`. With `--detect-only` the found-counters carry the whole report and every healed-counter is `0` — except `duplicates_cross_hour`, which is a *finding* the detector computes before any healing is attempted (it counts duplicate rows straddling an hour boundary, which a per-hour mint structurally cannot collapse) and is therefore reported under detect-only too. `backfill-trades` exits **2** when `primary_root` does not exist, **1** if the sweep recorded any error (a fetch failure, a mint failure, or a post-mint invariant violation), else **0**.

### `zcrypto panel`<a name="zcrypto-panel"></a>

The 1s L2 primitive panel: materializes the canonical book archive (reconciled-first) into a 1-second-grid, wide primitive panel — spread/mid/microprice/imbalance, effective-spread-at-size (`fill_bps_*`), and cumulative depth (`depth_qty_*`) — one row per second per pair. Each row also carries `stale_seconds`: seconds since the last message reached the book. The grid is dense, so an archive hole still emits rows — carrying a frozen, carried-forward book that `updates == 0` alone cannot distinguish from a quiet second. **Filter `stale_seconds > 30` to drop those; a null means the staleness is unknown, and is dropped by both `>` and `<=` comparisons.**

```bash
zcrypto panel materialize <primary_root> [reconciled_root] --panel-root <path>
```

| Argument / Option | Description |
| -- | -- |
| `primary_root` | The primary (raw) canonical book archive; must exist. |
| `reconciled_root` | Optional healed overlay; its hours materialize reconciled-first. Omit to use the primary alone. |
| `--panel-root` | The panel tree root to write into (required). |
| `--pair` | Only this pair (e.g. `BTC/EUR`); its quote must have a notional ladder (EUR, BTC). Defaults to every pair whose quote has one. |
| `--since` | Only hours at/after this UTC boundary: a `YYYY-MM-DD` date or an ISO-8601 hour (e.g. `2026-07-16T09`). |
| `--depth` | Book depth the archive was captured at (default `100`, capture's default). |
| `--allow-holes` | Proceed even if `--since` is newer than a pair's panel watermark, permanently skipping the hole in between. |
| `--settle-hours` | Defer hours newer than this (default `7`): the heal-settle margin so an hour is only materialized once the reconciler (H+6h max mint) has healed it, keeping the monotone watermark off the un-healed primary. |

`materialize` writes `<panel_root>/panel-meta.json` (schema version, grid, notional ladder, K-levels) on a fresh panel root, and **refuses** if an existing one's generation differs from the running code's — a generation change must be an explicit regeneration of the whole panel tree, never a silent mix.

The panel covers every pair whose quote has a notional ladder — currently EUR and BTC, spanning the whole point-in-time universe including its `ETH/BTC` / `SOL/BTC` relative-value legs. The ladder walks `price × qty`, denominated in the pair's *quote* currency; the BTC rungs are pinned EUR-equivalent rather than reusing the EUR figures directly, so the resulting `fill_bps_*` columns stay comparable in cost terms across both quotes. A pair whose quote has no ladder entry is skipped by the sweep — logged once per pair — and an explicit `--pair` on such a quote is refused rather than silently doing nothing.

Each pair is watermarked at its newest existing panel hour; a sweep only materializes hours strictly newer than that — **and only once they have settled** (`--settle-hours`, default 7h): a canonical hour is *final* well before it is *heal-complete*, since the reconciler mints the healed book overlay at H+2h…H+6h; taking an hour before then would let the monotone watermark permanently capture the un-healed primary. A newer, not-yet-settled hour is counted `hours_unsettled` and left for a later sweep. **`--since` that would open a gap above a pair's watermark — or above a fresh pair's earliest canonical hour — refuses by default**: skipping straight to `--since` would permanently strand the hours in `[watermark+1h, since)` once later hours advance the watermark past them. Pass `--allow-holes` to proceed anyway (a warning still names the pair, the watermark, and the stranded range).

`OrderBook` state is threaded across hours per pair: Kraken snapshots arrive on subscribe, not once per capture hour, so an hour opening with a plain update continues from the previous hour's end-of-hour book (persisted as a `<HH>.state.json` sidecar next to its parquet, enabling O(1) resume) rather than being rebuilt from nothing. An hour that cannot anchor — an update-opening hour with no carried book, e.g. after a gap in the archive — is counted in `hours_unanchored`: an honest gap, not a failure, logged once per contiguous run of them. A per-hour failure of any other kind is isolated and logged (`panel hour failed pair=... hour=...: ...`); the sweep continues past it. Exits **1** iff any hour errored (`hours_unanchored` never affects the exit code), else **0**.

### `zcrypto data`<a name="zcrypto-data"></a>

The hot-cluster dataset exchange: every research node — the workstation, the ops node — fetches the same small `hot/` working set from the NAS hub and pushes back only what it authored; a revision never overwrites a published file, it mints a sibling instead. Three clusters make up the full topology: **custody** (the unbackfillable capture archive + raw dumps, replicated once to the NAS, read in place), **hot** (the small working set every node fetches/pushes via this command), and **private** (per-node state — the engine store/journal — that never syncs). See `docs/reference/data-catalog-full.md` for the full inventory.

`fetch` additively mirrors the NAS `hot/` hub into the local data root, verifying newly fetched files against their manifest's `sha256` by default.

```bash
zcrypto data fetch
```

| Option | Description |
| -- | -- |
| `--no-verify` | Skip manifest hash verification of newly fetched files. |

`push` sends this node's authored sets (`[zcrypto.data].authored_sets`) to the configured `push_dest` — an ssh alias pinned by the NAS's forced rsync command, never the read-write NFS mount.

```bash
zcrypto data push
```

`rebuild` re-freezes or refreshes one or more sets from their sources (the OHLCVT dumps; the funding/snapshot/universe fetchers) and mints a new sibling directory — it never writes into the live set. By convention this runs on the workstation — the authoring node; the ops node is pull-only and only consumes frozen baskets via `fetch`. Its dump source (`nfs_mount_dir/kraken-ohlcvt-updates`) derives from the NAS mount root.

```bash
zcrypto data rebuild <SET>...
```

`ohlc-reach` is the exception to "from the OHLCVT dumps": it carries the **live** `ohlc-full` set forward using Kraken's public REST OHLC window, which serves the most recent ~720 bars per interval. That window recedes at a rate set by the interval — roughly 720 days at the daily grid, 120 days at 4h, but only 30 days at 1h — so a reach set is routinely **mixed**, and each series lands one of two ways:

- **continuous** (`<interval>.parquet`) — the REST window still overlaps the canonical tail, the seam was verified (at least 6 shared stamps, every shared close equal), and the merged series is drop-in compatible with any `ohlc-full` reader.
- **detached** (`<interval>.detached.parquet`) — the window no longer reaches the canonical tail. The bars are still written, because a REST bar is retrievable only while the window still reaches it; but they sit under a filename no `ohlc-full` reader globs, so a detached segment cannot be silently spliced across the gap. Promote it deliberately once an intervening dump closes the gap. Whether a detached capture is a *bridge* (a scheduled dump will cover the same span, so it just buys continuity earlier) or a *rescue* (nothing else will ever cover it) depends on the dump calendar — the set does not assume, so check before treating one as either.

`manifest.json` records the status per series — a reach set never makes one set-wide continuity claim. A run logs a WARNING naming every detached series. A seam that *overlaps but does not hold* (too few shared stamps, or a disagreeing close) is a hard error, not a fallback to detached: the canonical set is authoritative, so a contradiction there is a data-integrity failure rather than a gap.

| Argument / Option | Description |
| -- | -- |
| `SETS...` | Dataset names to rebuild: `ohlc-full`, `ohlc-reach`, `ohlc-15m`, `derivatives-funding`, `derivatives-oi`, `snapshots`, `universe`. |
| `--push` / `--no-push` | Push the minted sibling(s) to `push_dest` after rebuilding (default `--push`). |

All three exit **1** on a configuration or sync error (a missing/unmountable hot source `nfs_mount_dir/hot`, an unlisted authored set, an unknown rebuild set, a mismatched manifest hash, a `universe` rebuild whose resolved OHLC source (the newest `ohlc-reach-<stamp>` sibling, else `ohlc-full`) is staler than the 7-day budget, is missing any candidate leg, or whose `manifest.json` is missing/unreadable — the set then cannot identify itself, so no artifact is written), else **0**. The transport is always plain rsync `--archive --ignore-existing` — never `--delete` — so the append-only contract is enforced structurally: a content-changed file is simply untransmittable.

`derivatives-oi` backfills open-interest history from Binance Vision daily `metrics` dumps (5-minute `sum_open_interest` + the free long/short and taker ratios, back to each perp's listing) into `data/derivatives-oi/`, the sibling of `derivatives-funding` — the second free-backfillable B2 input. Both come from the public `data.binance.vision` CDN (checksum-verified per file); liquidations, the third B2 input, have no free dump and are collected live via Coinalyze instead (see `docs/open-topics/T0023-*`).

### `zcrypto research`<a name="zcrypto-research"></a>

Evaluates a committed system over a frozen dataset and, on request, appends the resulting trial to the registry. This is the only supported way to add a registry record: the fit reads every series through the capturing loader, and the file digests / row counts / time span that loader accumulated become the record's `datasets` block — so a record's dataset identity is what the run actually read, never a hash supplied alongside it.

```bash
zcrypto research eval --subject <NAME> --dataset <DIR> [OPTIONS]
```

| Option | Description |
| -- | -- |
| `--subject <NAME>` | System to evaluate: `record44-crossfreq` (the cross-frequency system; daily + 4h series) or `record33-combined` (the combined system; daily series). |
| `--dataset <DIR>` | Frozen dataset directory name under the repo's `data/` root, e.g. `ohlc-full`. |
| `--window START END` | Restrict every series to the inclusive ISO-8601 range. Default: full history. |
| `--register` | Append the result to the trial registry. Omitted, the command only reports. |
| `--iteration <S>` | Iteration label of the run. Required with `--register`. |
| `--family <S>` | Trial family this run belongs to. Required with `--register`. |
| `--spec-hash <S>` | Hash of the design this run implements. Required with `--register`. |
| `--verdict {adopt,reject,park}` | The run's verdict. Required with `--register`. |
| `--n-trials <N>` | Trials in this family **including** this one. Required with `--register`, and must exceed the count already recorded for that family — the registry refuses anything lower. |
| `--variant <S>` | Variant label within the family. |
| `--notes <S>` | Free-text notes stored with the record. |
| `--seed <N>` | Seed used by the run; repeat the flag for several. |
| `--registry <PATH>` | Registry file to append to. Defaults to the committed `docs/reference/trial-registry.jsonl`. |

The report names the metrics, the observed dataset block, and whether the dataset's own freeze record vouched for the bytes read (a dataset with no `manifest.json` reports as inert — nothing cross-checked the bytes). Exits **1** on an unknown subject (listing the known ones), on a dataset missing any series the subject needs (naming every missing file, before a single read), on a `--register` run missing one of its required flags, and when the registry refuses the record.

### `zcrypto tick`<a name="zcrypto-tick"></a>

Derives bars from the captured trade tape — the only fine-cadence source whose reach does not expire — and publishes them as one Parquet final per pair per UTC day (with a `.sha256` sidecar, written before the publishing rename).

```bash
zcrypto tick materialize <PRIMARY_ROOT> <OUT_ROOT> --reconciled-root <PATH> [OPTIONS]
```

| Argument / Option | Description |
| -- | -- |
| `PRIMARY_ROOT` | The primary (raw) canonical trade archive, laid out `BASE/QUOTE/trades/YYYY/MM/DD/HH.parquet`. |
| `OUT_ROOT` | Dataset root the daily finals are published into, as `BASE/QUOTE/YYYY/MM/DD.parquet`. |
| `--reconciled-root <PATH>` | The healed overlay, read first. **Required** — an optional overlay is one forgotten flag away from publishing the un-healed stream. |
| `--settle-hours <N>` | Hours past a day's end before it may be published (default `26`). |
| `--rescan-days <N>` | Trailing settled days re-attempted, so a late-healed day is still picked up (default `3`). |

The sweep publishes each settled day whose tape is measurably heal-complete (per-pair `trade_id` contiguity — an absent hour means a quiet hour, not a hole), skips days that already have a final, and isolates a failing day into the error list rather than aborting the pair. One line reports `days_written`, `days_skipped`, `days_unsettled`, `days_unhealed`, `days_gap` (settled, unpublished days that have fallen outside the re-scan window — permanent gaps), `rows`, and `errors`; each failure is then named on stderr as `pair`, day and message. Exits **1** if any day failed, else **0**.

A run against a fresh archive reports `days_unsettled` for its newest day (or two) and publishes nothing for it — that is the settle gate working, not a failure. The live-edge day is likewise held back until a later segment exists to prove its tail is not truncated.

## Configuration<a name="configuration"></a>

`zcrypto` reads configuration from **`zcrypto.toml`** in the current working directory (the repo root when running from the checkout). The file is committed with working defaults.

### `[zcrypto]`: dataset paths<a name="zcrypto-dataset-paths"></a>

```toml
[zcrypto]
data_dir = "data"                  # compiled dataset directory
nfs_mount_dir = "/mnt/zhao-crypto"  # NAS mount root: the hot/ fetch source and the custody sets (kraken-ohlcvt-updates, ...) derive from it
```

`data_dir` resolves via **flag → config → error**: if it is neither passed as a CLI flag nor set in `zcrypto.toml`, the command exits immediately with a clear error message (`ERROR: no data_dir configured — set [zcrypto].data_dir in zcrypto.toml or pass --data-dir <path>`). `nfs_mount_dir` instead has a built-in default (`/mnt/zhao-crypto`, aligned across the workstation and ops so one committed value serves both), so it always resolves; override it in `zcrypto.toml` only if a node mounts the NAS elsewhere.

### `[zcrypto.engine]`: shadow-engine settings<a name="zcryptoengine-shadow-engine-settings"></a>

Optional table tuning the `zcrypto engine` shadow node. Every key has a built-in default living **in code** — the committed `zcrypto.toml` does not set any of them; add a key only to override it. Unknown keys are rejected.

| Key | Default | Meaning |
| -- | -- | -- |
| `store_dir` | `data/engine-store` | The live price store: a per-pair × grid Parquet mirror of the canonical dataset, kept warm by REST gap-fills. |
| `journal_dir` | `data/engine-journal` | The cycle journal root: per-day success records, failed-cycle sidecars, input snapshots, and `orders.jsonl`. |
| `shadow_nav_eur` | `1000.0` | The shadow book's NAV; an intended order's notional is `Δtarget × shadow_nav_eur`. |
| `exec_enabled` | `false` | Attach the Kraken execution client to the node. Keep `false` off the VPS — the trade key is IP-bound, so local runs are keyless. |
| `exec_max_plan_notional_eur` | `100.0` | The total-notional cap a probe plan may carry — the blast-radius bound. |
| `settle_delay_secs` | `90` | Seconds after each 4h boundary before the cycle's first store refresh, letting the venue commit the boundary candle. |
