from pathlib import Path

import pytest
import yaml

from cli.config import (
    AppConfig,
    ConfigError,
    DataConfig,
    EngineConfig,
    FetchConfig,
    load_config,
    resolve_data_dir,
    resolve_hot_source,
    resolve_ohlcvt_source_dir,
    resolve_push_dest,
)


def _write(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "zcrypto.toml"
    p.write_text(body)
    return p


def test_absent_file_yields_none_paths_and_default_fetch(tmp_path):
    cfg = load_config(tmp_path / "zcrypto.toml")
    assert cfg.data_dir is None
    assert cfg.nfs_mount_dir == Path("/mnt/zhao-crypto")  # a real default always exists
    assert cfg.fetch == FetchConfig()
    assert cfg.engine == EngineConfig()


def test_reads_paths(tmp_path):
    cfg = load_config(
        _write(
            tmp_path,
            '[zcrypto]\ndata_dir = "data"\nnfs_mount_dir = "/mnt/nas"\n',
        )
    )
    assert cfg.data_dir == Path("data")
    assert cfg.nfs_mount_dir == Path("/mnt/nas")


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


@pytest.mark.parametrize("literal", ["nan", "inf", "-inf"])
def test_engine_non_finite_shadow_nav_raises(tmp_path, literal):
    # `nan`/`inf` are valid TOML floats and `nan <= 0` is False, so they cleared the positivity
    # check. The cycle writer would then fail its record's validation AFTER appending its orders,
    # leaving an orders block with no cycle record behind it -- so this must fail at load.
    with pytest.raises(ConfigError):
        load_config(_write(tmp_path, f"[zcrypto.engine]\nshadow_nav_eur = {literal}\n"))


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


def test_exec_armed_defaults_to_false_when_absent(tmp_path):
    cfg_path = tmp_path / "zcrypto.toml"
    cfg_path.write_text("[zcrypto.engine]\nexec_enabled = true\n")
    cfg = load_config(cfg_path)
    assert cfg.engine.exec_armed is False
    # The two flags are independent: connecting the transport never arms anything.
    assert cfg.engine.exec_enabled is True


def test_exec_armed_reads_true_when_set(tmp_path):
    cfg_path = tmp_path / "zcrypto.toml"
    cfg_path.write_text("[zcrypto.engine]\nexec_armed = true\n")
    assert load_config(cfg_path).engine.exec_armed is True


def test_exec_armed_rejects_a_non_boolean(tmp_path):
    cfg_path = tmp_path / "zcrypto.toml"
    cfg_path.write_text('[zcrypto.engine]\nexec_armed = "yes"\n')
    with pytest.raises(ConfigError, match="must be a boolean"):
        load_config(cfg_path)


def test_exec_max_plan_notional_eur_defaults_to_100_when_absent(tmp_path):
    cfg_path = tmp_path / "zcrypto.toml"
    cfg_path.write_text("[zcrypto.engine]\nexec_armed = true\n")
    cfg = load_config(cfg_path)
    assert cfg.engine.exec_max_plan_notional_eur == 100.0


def test_exec_max_plan_notional_eur_reads_a_set_value(tmp_path):
    cfg_path = tmp_path / "zcrypto.toml"
    cfg_path.write_text("[zcrypto.engine]\nexec_max_plan_notional_eur = 250\n")
    assert load_config(cfg_path).engine.exec_max_plan_notional_eur == 250.0


def test_exec_max_plan_notional_eur_rejects_a_non_number_non_positive_or_bool(tmp_path):
    cfg_path = tmp_path / "zcrypto.toml"
    # nan/inf are real TOML float literals; nan defeats every "<= 0" comparison (always False) and
    # inf disables the blast-radius bound entirely (nothing compares as "exceeding" it) -- both
    # must be refused explicitly, not admitted as "positive".
    for bad in ('"nope"', "0", "true", "nan", "inf"):
        cfg_path.write_text(f"[zcrypto.engine]\nexec_max_plan_notional_eur = {bad}\n")
        with pytest.raises(ConfigError, match="must be a positive number"):
            load_config(cfg_path)


def test_tracking_band_bps_is_unset_by_default(tmp_path):
    """The tracking-error trip ships DISARMED: an absent key is None, and None never trips. The
    default is what a fresh deployment gets, so it is the one value this must pin."""
    cfg_path = tmp_path / "zcrypto.toml"
    cfg_path.write_text("[zcrypto.engine]\nexec_armed = true\n")
    assert load_config(cfg_path).engine.tracking_band_bps is None


def test_tracking_band_bps_reads_a_set_value(tmp_path):
    cfg_path = tmp_path / "zcrypto.toml"
    cfg_path.write_text("[zcrypto.engine]\ntracking_band_bps = 120\n")
    assert load_config(cfg_path).engine.tracking_band_bps == 120.0


def test_tracking_band_bps_rejects_a_non_number_non_positive_or_bool(tmp_path):
    cfg_path = tmp_path / "zcrypto.toml"
    # `exec_max_plan_notional_eur`'s reasoning, in the opposite direction: nan defeats every
    # `mean > band` comparison (always False) and silently disarms the trip, inf does the same
    # explicitly, and zero or a negative band would trip on the first week ever scored.
    for bad in ('"nope"', "0", "-1.0", "true", "nan", "inf"):
        cfg_path.write_text(f"[zcrypto.engine]\ntracking_band_bps = {bad}\n")
        with pytest.raises(ConfigError, match="must be a positive number"):
            load_config(cfg_path)


def test_the_engine_role_template_renders_the_plan_cap_explicitly():
    """The blast-radius bound must appear in a converge diff, exactly like exec_armed."""
    text = Path("infra/ansible/roles/engine/templates/zcrypto.toml.j2").read_text()
    # Parsed, not substring: a commented-out line satisfies containment, and `100.01` contains
    # `100.0`. This is the live trade path's blast-radius cap -- it must be the real setting.
    assert any(ln.strip() == "exec_max_plan_notional_eur = {{ engine_exec_max_plan_notional_eur }}" for ln in text.splitlines()), (
        "the cap is not rendered into the engine config"
    )
    defaults = yaml.safe_load(Path("infra/ansible/roles/engine/defaults/main.yml").read_text())
    assert defaults["engine_exec_max_plan_notional_eur"] == 100.0, defaults.get("engine_exec_max_plan_notional_eur")


def test_committed_zcrypto_toml_has_no_engine_table():
    # the committed config stays unchanged — EngineConfig defaults live in code (spec precedent).
    cfg = load_config(Path("zcrypto.toml"))
    assert cfg.engine == EngineConfig()


def test_resolve_flag_wins(tmp_path):
    cfg = load_config(_write(tmp_path, '[zcrypto]\ndata_dir = "from_config"\n'))
    assert resolve_data_dir(Path("from_flag"), cfg) == Path("from_flag")


def test_resolve_ohlcvt_source_dir_flag_wins(tmp_path):
    cfg = load_config(_write(tmp_path, '[zcrypto]\nnfs_mount_dir = "/mnt/nas"\n'))
    assert resolve_ohlcvt_source_dir(Path("from_flag"), cfg) == Path("from_flag")


def test_resolve_ohlcvt_source_dir_derives_from_nfs_mount(tmp_path):
    cfg = load_config(_write(tmp_path, '[zcrypto]\nnfs_mount_dir = "/mnt/nas"\n'))
    assert resolve_ohlcvt_source_dir(None, cfg) == Path("/mnt/nas/kraken-ohlcvt-updates")
    # and with no config at all, from the default mount root
    assert resolve_ohlcvt_source_dir(None, load_config(tmp_path / "absent.toml")) == Path("/mnt/zhao-crypto/kraken-ohlcvt-updates")


def test_resolve_unconfigured_raises_with_both_remedies():
    cfg = AppConfig(
        data_dir=None, nfs_mount_dir=Path("/mnt/zhao-crypto"), fetch=FetchConfig(), engine=EngineConfig(), data=DataConfig()
    )
    with pytest.raises(ConfigError) as exc:
        resolve_data_dir(None, cfg)
    msg = str(exc.value)
    assert "--data-dir" in msg and "[zcrypto].data_dir" in msg


def test_removed_keys_are_rejected(tmp_path):
    with pytest.raises(ConfigError, match="unknown key"):
        load_config(_write(tmp_path, "[zcrypto.fetch]\nbackfill_right_edge_grace_days = 7\n"))


def test_data_config_defaults_when_absent(tmp_path):
    cfg = load_config(_write(tmp_path, "[zcrypto]\n"))
    assert cfg.data == DataConfig()


def test_data_config_parses_all_keys(tmp_path):
    cfg = load_config(
        _write(
            tmp_path,
            '[zcrypto.data]\npush_dest = "nas-hot:"\nauthored_sets = ["ohlc-full", "snapshots"]\n',
        )
    )
    assert cfg.data.push_dest == "nas-hot:"
    assert cfg.data.authored_sets == ("ohlc-full", "snapshots")


def test_data_config_unknown_key_raises(tmp_path):
    with pytest.raises(ConfigError, match="unknown key"):
        load_config(_write(tmp_path, '[zcrypto.data]\nhot_dir = "x"\n'))  # hot_dir is now removed → unknown


def test_data_config_rejects_bad_types(tmp_path):
    with pytest.raises(ConfigError):
        load_config(_write(tmp_path, '[zcrypto.data]\nauthored_sets = "ohlc-full"\n'))
    with pytest.raises(ConfigError):
        load_config(_write(tmp_path, '[zcrypto.data]\npush_dest = ""\n'))


def test_resolve_hot_source_derives_from_nfs_mount(tmp_path):
    cfg = load_config(_write(tmp_path, '[zcrypto]\nnfs_mount_dir = "/mnt/nas"\n'))
    assert resolve_hot_source(cfg) == Path("/mnt/nas/hot")
    assert resolve_hot_source(load_config(tmp_path / "absent.toml")) == Path("/mnt/zhao-crypto/hot")


def test_resolve_push_dest_unset_raises_and_set_returns(tmp_path):
    empty = load_config(_write(tmp_path, "[zcrypto]\n"))
    with pytest.raises(ConfigError):
        resolve_push_dest(empty)
    cfg = load_config(_write(tmp_path, '[zcrypto.data]\npush_dest = "nas-hot:"\n'))
    assert resolve_push_dest(cfg) == "nas-hot:"
