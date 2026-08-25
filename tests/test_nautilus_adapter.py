import nautilus_trader
from nautilus_trader.adapters.kraken import (
    KrakenDataClientConfig,
    KrakenDataClientFactory,
    KrakenExecutionClientConfig,
    KrakenExecutionClientFactory,
)


def test_pinned_version():
    # Pin is deliberate: docs/research/14.phase6-adapter-verification-1.230.0.md verifies the Kraken
    # adapter against 1.230.0, and a bump must still force a conscious re-verification
    # (see docs/specs/00039-phase6-kickoff-design.md). What moved is WHEN that re-verification
    # is owed: the attended ~EUR 0.20 order-semantics pass is a precondition of ARMING the engine
    # on this version, not of merging the bump. For 1.231.0 it RAN on 2026-08-23 --
    # docs/research/14.phase6-adapter-verification-1.231.0.md, PASS on all six probes -- and the
    # version is recorded in cli/engine/order-semantics-verified.json, which both arming guards
    # read. The next bump owes its own pass; infra/runbooks/order-semantics-verification.md.
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
    assert KrakenExecutionClientConfig is not None
    assert KrakenDataClientFactory is not None
    assert KrakenExecutionClientFactory is not None
