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
  - [`zcrypto engine`](#zcrypto-engine)
    - [Shadow soak service (systemd user unit)](#shadow-soak-service-systemd-user-unit)
    - [VPS journal pull and daily gate ops — retired (moved to the NAS, iter-094)](#vps-journal-pull-and-daily-gate-ops-%E2%80%94-retired-moved-to-the-nas-iter-094)
  - [`zcrypto archive`](#zcrypto-archive)
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
| `-h`, `--help` | Show help and exit. |

Running `zcrypto` with no options (or with `-h` / `--help`) prints the help.

### `zcrypto capture`<a name="zcrypto-capture"></a>

24/7 daemon that streams Kraken's **public** WS v2 feed (no API keys) — order book (depth 100) + trades — for the universe pairs, and writes hourly zstd-compressed Parquet segments (with a `.sha256` manifest per segment) for later backfill/analysis.

```bash
zcrypto capture [OPTIONS]
```

| Option | Description |
| -- | -- |
| `--pairs <PAIR>` | Pair to capture, e.g. `--pairs BTC/EUR`; repeat for multiple. Defaults to the EUR majors in `data/universe/point-in-time-universe.json`. |
| `--depth <INT>` | Order book depth: one of `10`, `25`, `100`, `500`, `1000` (default `100`). |
| `--data-dir <PATH>` | Segment output base directory. Defaults to `$ZCRYPTO_CAPTURE_DATA_DIR` if set, else `/var/lib/zcrypto-capture/segments`. |
| `--duration <SECS>` | Run for this many seconds then stop cleanly (for smoke-testing); omit to run until interrupted. |

Segments land at `<data-dir>/<pair>/{book,trades}/<YYYY>/<MM>/<DD>/<HH>.parquet`. Set `HEALTHCHECK_URL` (a healthchecks.io ping URL) to enable the dead-man's-switch liveness ping; it's optional and skipped when unset.

### `zcrypto liquidations`<a name="zcrypto-liquidations"></a>

24/7 daemon that streams Binance USD-M futures **liquidation** (`forceOrder`) events from the keyless combined stream `wss://fstream.binance.com/stream?streams=!forceOrder@arr` (no API keys) and writes hourly zstd-compressed Parquet segments (with a `.sha256` manifest per segment), one per symbol, reusing the capture `SegmentWriter`. Runs on the ops node (spec 00051 OPS-2); liquidations are not backfillable, so the segments replicate to the NAS.

```bash
zcrypto liquidations [OPTIONS]
```

| Option | Description |
| -- | -- |
| `--data-dir <PATH>` | Segment output base directory. Defaults to `$ZCRYPTO_LIQUIDATIONS_DATA_DIR` if set, else `/var/lib/zcrypto-ops/liquidations`. |
| `--duration <SECS>` | Run for this many seconds then stop cleanly (for smoke-testing); omit to run until interrupted. |

Segments land at `<data-dir>/<SYMBOL>/liquidations/<YYYY>/<MM>/<DD>/<HH>.parquet` (`<SYMBOL>` is the Binance ticker, e.g. `BTCUSDT`), with columns `ts, symbol, side, price, orig_qty, avg_price, order_status, event_id`. Redelivered events (Binance replays force-orders on reconnect) are de-duped on the synthesized `event_id`. Set `LIQUIDATIONS_HEALTHCHECK_URL` (a healthchecks.io ping URL) to enable the dead-man's-switch liveness ping; it's optional and skipped when unset.

### `zcrypto engine`<a name="zcrypto-engine"></a>

The Phase-6 shadow engine: a live price store seeded from the canonical dataset and kept warm by Kraken REST gap-fills, a Nautilus node that runs one shadow cycle per 4h UTC boundary (00/04/08/12/16/20), a per-day journal of cycle evidence (records, failed-cycle sidecars, input snapshots, `orders.jsonl`), and replay/report verification against the ratified concordance gate. Settings come from the [`[zcrypto.engine]`](#zcryptoengine-shadow-engine-settings) table.

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
| `gate-export --textfile <PATH> [--journal-dir <PATH>] [--healthcheck-url <URL>] [--lag-fail-seconds <SECS>]` | Evaluate the gate (same replay-on-demand pass as `report`) and atomically write it as a Prometheus node-exporter textfile, then ping an independent dead-man's-switch healthcheck. Emits `zcrypto_gate_status` (1/0), `zcrypto_gate_streak_days`, `zcrypto_gate_journal_pull_lag_seconds` (omitted when the journal is empty), `zcrypto_gate_mismatch_total` (every not-clean cycle: replay mismatches + validation failures + failed-cycle sidecars), and `zcrypto_gate_export_timestamp_seconds`. `--healthcheck-url` pings clean (GET the URL) iff `mismatch_total == 0` and the journal-pull lag is within `--lag-fail-seconds` (default `18000`, 5h); otherwise pings `<url>/fail`. Omit `--healthcheck-url` to skip the ping. Exits 0 even when the gate has a mismatch or is stale (those are findings, surfaced via the metrics/ping); non-zero only on an operational failure (unreadable journal, unwritable textfile). |

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

#### VPS journal pull and daily gate ops — retired (moved to the NAS, iter-094)<a name="vps-journal-pull-and-daily-gate-ops-%E2%80%94-retired-moved-to-the-nas-iter-094"></a>

**Retired.** The daily gate ops (journal pull → verified replay → report) ran on the workstation as a systemd `--user` timer; it lagged whenever the workstation was offline. It is superseded by **Role B** on the always-on NAS — the `archive-pull` container pulls the journal and runs `zcrypto engine gate-export` (fast-path gate scoring, emitted to Grafana + a dead-man ping) on every cycle (spec `docs/specs/00049-role-b-nas-gate-verify-design.md`, `infra/nas/`). The `infra/systemd/zcrypto-engine-gateops.{service,timer}` templates are removed.

On a workstation that still has the old timer installed, disable it:

```bash
systemctl --user disable --now zcrypto-engine-gateops.timer
rm -f ~/.config/systemd/user/zcrypto-engine-gateops.service ~/.config/systemd/user/zcrypto-engine-gateops.timer ~/.ssh/zcrypto-sync_ed25519
systemctl --user daemon-reload
```

### `zcrypto archive`<a name="zcrypto-archive"></a>

The always-on NAS pull/archive tier (Role A, spec `00048`): pull a source tree via rsync-over-ssh, then hash-verify every segment against its `.sha256` manifest sidecar.

```bash
zcrypto archive pull <source> <dest>
```

| Argument | Description |
| -- | -- |
| `source` | rsync source spec, e.g. `deploy@host:/var/lib/zcrypto-capture/segments/`. |
| `dest` | Local destination directory to rsync into and verify. |

`pull` exits **2** on an rsync transport failure (a partial pull is never verified as authoritative — this also covers a missing `ARCHIVE_SSH_KEY`), **1** if any pulled segment fails its manifest hash check, else **0**. The rsync-over-ssh transport reads `ARCHIVE_SSH_KEY` (the private key path, required), `ARCHIVE_SSH_PORT` (default `10022`), and `ARCHIVE_SSH_KNOWN_HOSTS` (a `UserKnownHostsFile` path). Host-key checking is strict (`StrictHostKeyChecking=yes`), so `ARCHIVE_SSH_KNOWN_HOSTS` must be pre-seeded with the remote host key — an unknown or changed key fails the pull closed rather than trusting it.

`reconcile` (Role C, spec `00050`) reads the two raw capture mirrors and mints healed hours into a separate overlay root, leaving both mirrors immutable and canonical-by-default.

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

**`--detect-only` is the default and must stay so until T0039's soak lands.** `--min-gap-seconds` is not yet validated cross-host: the measured single-host *maximum* natural quiescence is 14.78 s and a single secondary update row is enough to witness a gap, so a per-connection coalescing artifact could plausibly trip a **phantom splice** — an unaudited data swap into an archive that cannot be backfilled. Detect-only ledgers every `would_mint` and writes no parquet; `--mint` is unlocked only once the soak has pinned the threshold from real cross-host data.

An hour is considered once `now ≥ H + 2h` (finalization plus one pull cycle have both had time to land), and a hour still missing from the primary past `H + 6h` is minted from the complete secondary alone. Healing is **whole-window** for books (a secondary block is spliced in, never row-interleaved — L2 rows carry absolute quantities) and **row-level** for trades (`trade_id` is globally unique across hosts). Every decision is appended to `<reconciled_root>/reconcile-ledger.jsonl` (states `minted`, `would_mint`, `trade_deficit`, `both_streams_silent`, `total_loss`, `failed`), and each minted final gets a `.sha256` sidecar plus an `<HH>.provenance.json`, so the overlay verifies with the same `verify_tree` as a raw mirror.

Two **correlated-loss** detectors run regardless of the flag and never mint: `both_streams_silent` (every pair silent on *both* hosts in the *same* window — at depth 100 that has no benign explanation) and `total_loss` (an hour absent from both mirrors while real data brackets it on either side). When both streams are dark there is no witness to heal with, so the loss is permanent: it is ledgered, booked into `zcrypto_reconcile_residual_gap_seconds_total`, and paged.

`reconcile` exits **2** when a mirror is unreadable (transport), **1** on an integrity failure (an unreadable segment, a non-monotonic stream, a corrupt ledger — no textfile is published, so `last_success_timestamp` goes stale and pages), else **0**. Residual gaps are a *finding*, not a failure: they exit 0 and page through the metric.

## Configuration<a name="configuration"></a>

`zcrypto` reads configuration from **`zcrypto.toml`** in the current working directory (the repo root when running from the checkout). The file is committed with working defaults.

### `[zcrypto]`: dataset paths<a name="zcrypto-dataset-paths"></a>

```toml
[zcrypto]
data_dir = "data"                                                   # compiled dataset directory
backup_dir = "../zcrypto-kraken-data/zcrypto"                       # durable backup root (raw/ mirror + snapshots/)
ohlcvt_source_dir = "../zcrypto-kraken-data/kraken-ohlcvt-updates"  # Kraken OHLCVT full-history ZIP archive (base dump + quarterly updates)
```

Paths resolve via **flag → config → error**: if a path is neither passed as a CLI flag nor set in `zcrypto.toml`, the command exits immediately with a clear error message (`ERROR: no <name> configured — set [zcrypto].<name> in zcrypto.toml or pass --<flag> <path>`). There is no built-in fallback.

### `[zcrypto.engine]`: shadow-engine settings<a name="zcryptoengine-shadow-engine-settings"></a>

Optional table tuning the `zcrypto engine` shadow node. Every key has a built-in default living **in code** — the committed `zcrypto.toml` does not set any of them; add a key only to override it. Unknown keys are rejected.

| Key | Default | Meaning |
| -- | -- | -- |
| `store_dir` | `data/engine-store` | The live price store: a per-pair × grid Parquet mirror of the canonical dataset, kept warm by REST gap-fills. |
| `journal_dir` | `data/engine-journal` | The cycle journal root: per-day success records, failed-cycle sidecars, input snapshots, and `orders.jsonl`. |
| `shadow_nav_eur` | `1000.0` | The shadow book's NAV; an intended order's notional is `Δtarget × shadow_nav_eur`. |
| `exec_enabled` | `false` | Attach the Kraken execution client to the node. Keep `false` off the VPS — the trade key is IP-bound, so local runs are keyless. |
| `settle_delay_secs` | `90` | Seconds after each 4h boundary before the cycle's first store refresh, letting the venue commit the boundary candle. |
