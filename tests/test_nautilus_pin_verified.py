from cli.engine import execgate


def test_the_installed_nautilus_trader_is_one_the_order_semantics_record_verifies():
    installed = execgate._installed_nautilus_version()
    assert installed, "nautilus_trader does not import"
    assert installed in execgate._verified_nautilus_versions(), (
        f"nautilus-trader {installed} has no attended order-semantics pass in cli/engine/order-semantics-verified.json, "
        "so the engine refuses to arm on it: a bump lands only with that pass recorded on its own branch "
        "(docs/reference/adapter-verification/<version>.md), never by adding the version to the record to turn this green"
    )
