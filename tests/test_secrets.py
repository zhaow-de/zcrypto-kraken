from __future__ import annotations

from pathlib import Path

import pytest

from cli.secrets import KrakenCredentials, SecretsError, load_dotenv, load_kraken_credentials


def _write_env(tmp_path: Path, body: str) -> Path:
    p = tmp_path / ".env"
    p.write_text(body)
    return p


def test_load_dotenv_parses_key_value(tmp_path):
    path = _write_env(tmp_path, "KRAKEN_API_KEY=abc123\nKRAKEN_API_SECRET=def456\n")
    assert load_dotenv(path) == {"KRAKEN_API_KEY": "abc123", "KRAKEN_API_SECRET": "def456"}


def test_load_dotenv_skips_blank_lines_and_comments(tmp_path):
    path = _write_env(tmp_path, "# a comment\n\nKRAKEN_API_KEY=abc123\n")
    assert load_dotenv(path) == {"KRAKEN_API_KEY": "abc123"}


def test_load_dotenv_handles_export_prefix(tmp_path):
    path = _write_env(tmp_path, "export KRAKEN_API_KEY=abc123\n")
    assert load_dotenv(path) == {"KRAKEN_API_KEY": "abc123"}


def test_load_dotenv_strips_matching_surrounding_quotes(tmp_path):
    path = _write_env(tmp_path, "KRAKEN_API_KEY=\"abc123\"\nKRAKEN_API_SECRET='def456'\n")
    assert load_dotenv(path) == {"KRAKEN_API_KEY": "abc123", "KRAKEN_API_SECRET": "def456"}


def test_load_dotenv_missing_file_returns_empty_dict(tmp_path):
    assert load_dotenv(tmp_path / "nope.env") == {}


def test_load_dotenv_malformed_line_raises(tmp_path):
    path = _write_env(tmp_path, "not_a_kv_line\n")
    with pytest.raises(SecretsError):
        load_dotenv(path)


def test_load_kraken_credentials_both_present_via_env(tmp_path):
    creds = load_kraken_credentials(env={"KRAKEN_API_KEY": "k", "KRAKEN_API_SECRET": "s"}, dotenv_path=tmp_path / ".env")
    assert creds == KrakenCredentials(api_key="k", api_secret="s")


def test_load_kraken_credentials_neither_present_returns_none(tmp_path):
    assert load_kraken_credentials(env={}, dotenv_path=tmp_path / ".env") is None


def test_load_kraken_credentials_one_present_raises(tmp_path):
    with pytest.raises(SecretsError):
        load_kraken_credentials(env={"KRAKEN_API_KEY": "k"}, dotenv_path=tmp_path / ".env")


def test_load_kraken_credentials_falls_back_to_dotenv_file(tmp_path):
    path = _write_env(tmp_path, "KRAKEN_API_KEY=file_key\nKRAKEN_API_SECRET=file_secret\n")
    creds = load_kraken_credentials(env={}, dotenv_path=path)
    assert creds == KrakenCredentials(api_key="file_key", api_secret="file_secret")


def test_load_kraken_credentials_env_takes_precedence_over_dotenv(tmp_path):
    path = _write_env(tmp_path, "KRAKEN_API_KEY=file_key\nKRAKEN_API_SECRET=file_secret\n")
    creds = load_kraken_credentials(env={"KRAKEN_API_KEY": "env_key", "KRAKEN_API_SECRET": "env_secret"}, dotenv_path=path)
    assert creds == KrakenCredentials(api_key="env_key", api_secret="env_secret")


def test_load_kraken_credentials_defaults_to_os_environ(tmp_path, monkeypatch):
    monkeypatch.setenv("KRAKEN_API_KEY", "envk")
    monkeypatch.setenv("KRAKEN_API_SECRET", "envs")
    creds = load_kraken_credentials(dotenv_path=tmp_path / ".env")
    assert creds == KrakenCredentials(api_key="envk", api_secret="envs")
