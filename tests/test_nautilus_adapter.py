import nautilus_trader
from nautilus_trader.adapters.kraken.config import KrakenDataClientConfig, KrakenExecClientConfig
from nautilus_trader.adapters.kraken.factories import KrakenLiveDataClientFactory, KrakenLiveExecClientFactory


def test_pinned_version():
    # Pin is deliberate: docs/research/14.phase6-adapter-verification.md verifies the Kraken
    # adapter against 1.230.0, and a bump must still force a conscious re-verification
    # (see docs/specs/00039-phase6-kickoff-design.md). What moved is WHEN that re-verification
    # is owed: the attended ~EUR 0.20 order-semantics pass is now a precondition of ARMING the
    # engine on this version, not of merging the bump. It has NOT run for 1.231.0 -- the arming
    # checklist in infra/runbooks/engine.md is where that obligation is enforced.
    assert nautilus_trader.__version__ == "1.231.0"


def test_the_gates_version_reader_reports_the_really_installed_version():
    """The production reader's only direct true-positive. Every gate test injects a reader or
    patches this function, so an always-'' implementation -- a renamed attribute, a swallowed
    import error -- would ship green while making the arming gate refuse unconditionally. Asserted
    here because this module already imports nautilus_trader and pays the cost anyway."""
    from cli.engine.execgate import _installed_nautilus_version

    assert _installed_nautilus_version() == nautilus_trader.__version__
    assert _installed_nautilus_version() != ""


def test_kraken_adapter_config_and_factories_import():
    assert KrakenDataClientConfig is not None
    assert KrakenExecClientConfig is not None
    assert KrakenLiveDataClientFactory is not None
    assert KrakenLiveExecClientFactory is not None
