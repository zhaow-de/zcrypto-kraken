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
  - [`zcrypto engine`](#zcrypto-engine)
    - [Shadow soak service (systemd user unit)](#shadow-soak-service-systemd-user-unit)
    - [VPS journal pull and daily gate ops (systemd user timer)](#vps-journal-pull-and-daily-gate-ops-systemd-user-timer)
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

#### VPS journal pull and daily gate ops (systemd user timer)<a name="vps-journal-pull-and-daily-gate-ops-systemd-user-timer"></a>

One-time setup: the sync private key is ansible-vault-encrypted in git (`infra/ansible/files/sync_ed25519`), so decrypt a working copy to `~/.ssh` — never `ansible-vault decrypt` in place, which would rewrite the tracked file as plaintext key material one `git add` away from being committed:

```bash
umask 077; uv run ansible-vault view --vault-password-file infra/ansible/scripts/vault-pass.sh \
  infra/ansible/files/sync_ed25519 > ~/.ssh/zcrypto-sync_ed25519    # verify: 0600
```

Pull the VPS node's journal to the workstation (the rrsync forced command on the sync key pins the remote side to the journal subtree, so no remote source path is given):

```bash
rsync -az -e "ssh -i ~/.ssh/zcrypto-sync_ed25519 -o IdentitiesOnly=yes -p 10022" deploy@<vps-host>: data/engine-journal-vps/
```

`infra/systemd/zcrypto-engine-gateops.{service,timer}` (workstation **user** units) automate the daily gate ops: pull, then `replay --journal-dir data/engine-journal-vps --path verified` for UTC-yesterday, then `report --journal-dir data/engine-journal-vps` — report still runs when replay fails, and the replay's exit code is preserved. The timer fires daily at **06:30 UTC**, when all of UTC-yesterday's cycles are complete. Install (mirroring the soak unit's walkthrough; run the first pull attended before enabling the timer):

```bash
mkdir -p ~/.config/systemd/user
cp infra/systemd/zcrypto-engine-gateops.service infra/systemd/zcrypto-engine-gateops.timer ~/.config/systemd/user/
# fill in the copied service unit's placeholders: <repo> (absolute checkout path),
# <uv> (absolute uv path, `command -v uv`), <vps-host> (the VPS hostname/IP)
systemctl --user daemon-reload
systemctl --user enable --now zcrypto-engine-gateops.timer     # the TIMER is what's enabled, not the service
systemctl --user list-timers zcrypto-engine-gateops.timer      # confirm: next trigger at 06:30 UTC
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

`pull` exits **2** on an rsync transport failure (a partial pull is never verified as authoritative), **1** if any pulled segment fails its manifest hash check, else **0**. The rsync-over-ssh transport reads `ARCHIVE_SSH_KEY` (the private key path, required) and `ARCHIVE_SSH_PORT` (default `10022`).

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
