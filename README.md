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
  - [Configuration](#configuration)
    - [`[zcrypto]`: dataset paths](#zcrypto-dataset-paths)

<!-- mdformat-toc end -->

## Requirements<a name="requirements"></a>

- **Python 3.14** (pinned in `.python-version`).
- **[uv](https://docs.astral.sh/uv/)** — run `uv sync` to install/refresh the locked environment.

## Usage<a name="usage"></a>

```bash
zcrypto [OPTIONS]          # or: uv run python -m cli [OPTIONS]
```

| Option                                   | Description                                                             |
| ---------------------------------------- | ----------------------------------------------------------------------- |
| `-v`, `--version`                        | Show the application version and exit.                                  |
| `-l`, `--log <path>`                     | Append JSONL logs to this file. If unset, plain-text logs go to stdout. |
| `--log-level {DEBUG,INFO,WARNING,ERROR}` | Log threshold (default `INFO`). Applies to the `zcrypto.*` loggers.     |
| `-h`, `--help`                           | Show help and exit.                                                     |

Running `zcrypto` with no options (or with `-h` / `--help`) prints the help.

### `zcrypto capture`<a name="zcrypto-capture"></a>

24/7 daemon that streams Kraken's **public** WS v2 feed (no API keys) — order book (depth 100) + trades — for the universe pairs, and writes hourly zstd-compressed Parquet segments (with a `.sha256` manifest per segment) for later backfill/analysis.

```bash
zcrypto capture [OPTIONS]
```

| Option              | Description                                                                                                                              |
| ------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| `--pairs <PAIR>`    | Pair to capture, e.g. `--pairs BTC/EUR`; repeat for multiple. Defaults to the EUR majors in `data/universe/point-in-time-universe.json`. |
| `--depth <INT>`     | Order book depth: one of `10`, `25`, `100`, `500`, `1000` (default `100`).                                                               |
| `--data-dir <PATH>` | Segment output base directory. Defaults to `$ZCRYPTO_CAPTURE_DATA_DIR` if set, else `/var/lib/zcrypto-capture/segments`.                 |
| `--duration <SECS>` | Run for this many seconds then stop cleanly (for smoke-testing); omit to run until interrupted.                                          |

Segments land at `<data-dir>/<pair>/{book,trades}/<YYYY>/<MM>/<DD>/<HH>.parquet`. Set `HEALTHCHECK_URL` (a healthchecks.io ping URL) to enable the dead-man's-switch liveness ping; it's optional and skipped when unset.

### Configuration<a name="configuration"></a>

`zcrypto` reads configuration from **`zcrypto.toml`** in the current working directory (the repo root when running from the checkout). The file is committed with working defaults.

#### `[zcrypto]`: dataset paths<a name="zcrypto-dataset-paths"></a>

```toml
[zcrypto]
data_dir = "data"                                                   # compiled dataset directory
backup_dir = "../zcrypto-kraken-data/zcrypto"                       # durable backup root (raw/ mirror + snapshots/)
ohlcvt_source_dir = "../zcrypto-kraken-data/kraken-ohlcvt-updates"  # Kraken OHLCVT full-history ZIP archive (base dump + quarterly updates)
```

Paths resolve via **flag → config → error**: if a path is neither passed as a CLI flag nor set in `zcrypto.toml`, the command exits immediately with a clear error message (`ERROR: no <name> configured — set [zcrypto].<name> in zcrypto.toml or pass --<flag> <path>`). There is no built-in fallback.
