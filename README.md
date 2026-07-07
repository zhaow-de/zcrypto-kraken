![Version](https://img.shields.io/badge/version-v0.0.0-blue)
![GitHub License](https://img.shields.io/github/license/zhaow-de/zcrypto-kraken)
![Python Version from PEP 621 TOML](https://img.shields.io/python/required-version-toml?tomlFilePath=https://raw.githubusercontent.com/zhaow-de/zcrypto-kraken/develop/pyproject.toml)
![Coveralls](https://img.shields.io/coverallsCoverage/github/zhaow-de/zcrypto-kraken)

# zcrypto

Learning-for-Fun quant-trading research project for Kraken (spot + spot-margin).

<!-- mdformat-toc start --slug=github --maxlevel=4 --minlevel=2 -->

- [Requirements](#requirements)
- [Usage](#usage)
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

`zcrypto` currently exposes **no subcommands** — only the global options above. Running it with no options (or with `-h` / `--help`) prints the help.

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
