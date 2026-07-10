import nautilus_trader
from nautilus_trader.adapters.kraken.config import KrakenDataClientConfig, KrakenExecClientConfig
from nautilus_trader.adapters.kraken.factories import KrakenLiveDataClientFactory, KrakenLiveExecClientFactory


def test_pinned_version():
    # Pin is deliberate: docs/research/14.phase6-adapter-verification.md verifies the Kraken
    # adapter against this exact version, so a bump must consciously re-run that verification
    # (see docs/specs/00039-phase6-kickoff-design.md).
    assert nautilus_trader.__version__ == "1.230.0"


def test_kraken_adapter_config_and_factories_import():
    assert KrakenDataClientConfig is not None
    assert KrakenExecClientConfig is not None
    assert KrakenLiveDataClientFactory is not None
    assert KrakenLiveExecClientFactory is not None
