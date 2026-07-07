from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

__all__ = ["SecretsError", "KrakenCredentials", "load_dotenv", "load_kraken_credentials"]


class SecretsError(Exception):
    """A .env file is malformed, or Kraken credentials are only partially configured."""


@dataclass(frozen=True)
class KrakenCredentials:
    api_key: str
    api_secret: str


def load_dotenv(path: Path = Path(".env")) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("export "):
            stripped = stripped[len("export ") :].strip()
        if "=" not in stripped:
            raise SecretsError(f"malformed line in {path} (missing '='): {line!r}")
        key, _, value = stripped.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        values[key] = value
    return values


def load_kraken_credentials(*, env: Mapping[str, str] | None = None, dotenv_path: Path = Path(".env")) -> KrakenCredentials | None:
    env = env if env is not None else os.environ
    dotenv_values = load_dotenv(dotenv_path)

    def _resolve(name: str) -> str | None:
        return env.get(name) or dotenv_values.get(name) or None

    api_key = _resolve("KRAKEN_API_KEY")
    api_secret = _resolve("KRAKEN_API_SECRET")

    if api_key and api_secret:
        return KrakenCredentials(api_key=api_key, api_secret=api_secret)
    if not api_key and not api_secret:
        return None
    raise SecretsError("incomplete Kraken credentials: set both KRAKEN_API_KEY and KRAKEN_API_SECRET, not just one")
