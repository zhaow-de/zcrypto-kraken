from pathlib import Path

import pytest

from cli.config import (
    AppConfig,
    ConfigError,
    EngineConfig,
    FetchConfig,
    load_config,
    resolve_data_dir,
    resolve_ohlcvt_source_dir,
)


def _write(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "zcrypto.toml"
    p.write_text(body)
    return p


def test_absent_file_yields_none_paths_and_default_fetch(tmp_path):
    cfg = load_config(tmp_path / "zcrypto.toml")
    assert cfg.data_dir is None
    assert cfg.ohlcvt_source_dir is None
    assert cfg.fetch == FetchConfig()
    assert cfg.engine == EngineConfig()


def test_reads_paths(tmp_path):
    cfg = load_config(
        _write(
            tmp_path,
            '[zcrypto]\ndata_dir = "data"\nohlcvt_source_dir = "../zcrypto-ohlcvt"\n',
        )
    )
    assert cfg.data_dir == Path("data")
    assert cfg.ohlcvt_source_dir == Path("../zcrypto-ohlcvt")


def test_missing_one_path_key_is_none(tmp_path):
    cfg = load_config(_write(tmp_path, '[zcrypto]\ndata_dir = "data"\n'))
    assert cfg.data_dir == Path("data")


def test_fetch_override_merges_over_defaults(tmp_path):
    cfg = load_config(_write(tmp_path, "[zcrypto.fetch]\nfetch_concurrency = 3\n"))
    assert cfg.fetch.fetch_concurrency == 3
    assert cfg.fetch.http_timeout_get_secs == 60  # untouched default


def test_malformed_toml_raises(tmp_path):
    with pytest.raises(ConfigError):
        load_config(_write(tmp_path, "this is = = not toml"))


def test_zcrypto_not_a_table_raises(tmp_path):
    # [zcrypto] present but bound to a scalar (not a table) is malformed config.
    with pytest.raises(ConfigError):
        load_config(_write(tmp_path, "zcrypto = 5\n"))


def test_fetch_not_a_table_raises(tmp_path):
    # [zcrypto].fetch present but bound to a scalar (not a table) is malformed config.
    with pytest.raises(ConfigError):
        load_config(_write(tmp_path, "[zcrypto]\nfetch = 5\n"))


def test_non_string_path_raises(tmp_path):
    with pytest.raises(ConfigError):
        load_config(_write(tmp_path, "[zcrypto]\ndata_dir = 5\n"))


def test_non_positive_fetch_value_raises(tmp_path):
    with pytest.raises(ConfigError):
        load_config(_write(tmp_path, "[zcrypto.fetch]\nfetch_concurrency = 0\n"))


def test_non_int_fetch_value_raises(tmp_path):
    with pytest.raises(ConfigError):
        load_config(_write(tmp_path, '[zcrypto.fetch]\nfetch_concurrency = "x"\n'))


def test_unknown_fetch_key_raises(tmp_path):
    with pytest.raises(ConfigError):
        load_config(_write(tmp_path, "[zcrypto.fetch]\nnope = 1\n"))


def test_bool_fetch_value_raises(tmp_path):
    # bool is a subclass of int; it must be rejected, not silently accepted as 1.
    with pytest.raises(ConfigError):
        load_config(_write(tmp_path, "[zcrypto.fetch]\nfetch_concurrency = true\n"))


def test_engine_defaults_when_table_absent(tmp_path):
    cfg = load_config(_write(tmp_path, '[zcrypto]\ndata_dir = "data"\n'))
    assert cfg.engine == EngineConfig()


def test_engine_override_merges_over_defaults(tmp_path):
    cfg = load_config(
        _write(
            tmp_path,
            '[zcrypto.engine]\nstore_dir = "elsewhere/store"\nshadow_nav_eur = 2500\nexec_enabled = true\nsettle_delay_secs = 45\n',
        )
    )
    assert cfg.engine.store_dir == Path("elsewhere/store")
    assert cfg.engine.journal_dir == Path("data/engine-journal")  # untouched default
    assert cfg.engine.shadow_nav_eur == 2500.0
    assert cfg.engine.exec_enabled is True
    assert cfg.engine.settle_delay_secs == 45


def test_engine_not_a_table_raises(tmp_path):
    with pytest.raises(ConfigError):
        load_config(_write(tmp_path, "[zcrypto]\nengine = 5\n"))


def test_engine_unknown_key_raises(tmp_path):
    with pytest.raises(ConfigError):
        load_config(_write(tmp_path, "[zcrypto.engine]\nnope = 1\n"))


def test_engine_non_string_dir_raises(tmp_path):
    with pytest.raises(ConfigError):
        load_config(_write(tmp_path, "[zcrypto.engine]\nstore_dir = 5\n"))


def test_engine_empty_string_dir_raises(tmp_path):
    with pytest.raises(ConfigError):
        load_config(_write(tmp_path, '[zcrypto.engine]\nstore_dir = "  "\n'))


def test_engine_non_positive_shadow_nav_raises(tmp_path):
    with pytest.raises(ConfigError):
        load_config(_write(tmp_path, "[zcrypto.engine]\nshadow_nav_eur = 0\n"))


def test_engine_bool_shadow_nav_raises(tmp_path):
    # bool is a subclass of int/float — must be rejected, not silently accepted as 1.
    with pytest.raises(ConfigError):
        load_config(_write(tmp_path, "[zcrypto.engine]\nshadow_nav_eur = true\n"))


def test_engine_shadow_nav_accepts_float(tmp_path):
    cfg = load_config(_write(tmp_path, "[zcrypto.engine]\nshadow_nav_eur = 1500.5\n"))
    assert cfg.engine.shadow_nav_eur == 1500.5


def test_engine_exec_enabled_int_raises(tmp_path):
    # exec_enabled must be a real bool — 1 is not accepted as truthy.
    with pytest.raises(ConfigError):
        load_config(_write(tmp_path, "[zcrypto.engine]\nexec_enabled = 1\n"))


def test_engine_settle_delay_secs_bool_raises(tmp_path):
    # bool is a subclass of int — must be rejected, not silently accepted as 1.
    with pytest.raises(ConfigError):
        load_config(_write(tmp_path, "[zcrypto.engine]\nsettle_delay_secs = true\n"))


def test_engine_settle_delay_secs_non_positive_raises(tmp_path):
    with pytest.raises(ConfigError):
        load_config(_write(tmp_path, "[zcrypto.engine]\nsettle_delay_secs = 0\n"))


def test_engine_settle_delay_secs_non_int_raises(tmp_path):
    with pytest.raises(ConfigError):
        load_config(_write(tmp_path, '[zcrypto.engine]\nsettle_delay_secs = "x"\n'))


def test_committed_zcrypto_toml_has_no_engine_table():
    # the committed config stays unchanged — EngineConfig defaults live in code (spec precedent).
    cfg = load_config(Path("zcrypto.toml"))
    assert cfg.engine == EngineConfig()


def test_resolve_flag_wins(tmp_path):
    cfg = load_config(_write(tmp_path, '[zcrypto]\ndata_dir = "from_config"\n'))
    assert resolve_data_dir(Path("from_flag"), cfg) == Path("from_flag")


def test_resolve_ohlcvt_source_dir_flag_wins(tmp_path):
    cfg = load_config(_write(tmp_path, '[zcrypto]\nohlcvt_source_dir = "from_config"\n'))
    assert resolve_ohlcvt_source_dir(Path("from_flag"), cfg) == Path("from_flag")


def test_resolve_ohlcvt_source_dir_falls_back_to_config(tmp_path):
    cfg = load_config(_write(tmp_path, '[zcrypto]\nohlcvt_source_dir = "cfg_ohlcvt"\n'))
    assert resolve_ohlcvt_source_dir(None, cfg) == Path("cfg_ohlcvt")


def test_resolve_unconfigured_raises_with_both_remedies():
    cfg = AppConfig(data_dir=None, ohlcvt_source_dir=None, fetch=FetchConfig(), engine=EngineConfig())
    with pytest.raises(ConfigError) as exc:
        resolve_data_dir(None, cfg)
    msg = str(exc.value)
    assert "--data-dir" in msg and "[zcrypto].data_dir" in msg


def test_resolve_ohlcvt_source_dir_unconfigured_raises_with_both_remedies():
    cfg = AppConfig(data_dir=None, ohlcvt_source_dir=None, fetch=FetchConfig(), engine=EngineConfig())
    with pytest.raises(ConfigError) as exc:
        resolve_ohlcvt_source_dir(None, cfg)
    msg = str(exc.value)
    assert "--ohlcvt-source-dir" in msg and "[zcrypto].ohlcvt_source_dir" in msg


def test_removed_keys_are_rejected(tmp_path):
    with pytest.raises(ConfigError, match="unknown key"):
        load_config(_write(tmp_path, "[zcrypto.fetch]\nbackfill_right_edge_grace_days = 7\n"))
